from rest_framework.viewsets import ViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from django.apps import apps
from django.db.models import Q, CharField, TextField, Value, FloatField, F
from django.contrib.postgres.search import TrigramSimilarity
from guardian.shortcuts import get_objects_for_user
from rest_framework import serializers
from django.db.models.functions import Greatest, Coalesce, Cast

class GenericSearchPagination(LimitOffsetPagination):
    default_limit = 10
    max_limit = 100

class GenericSearchResultSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()
    highlights = serializers.SerializerMethodField()
    model = serializers.SerializerMethodField()

    class Meta:
        model = None
        fields = ["id", "text", "highlights", "model"]

    def get_text(self, obj):
        return str(obj)

    def get_highlights(self, obj):
        highlights = getattr(obj, '_matched_fields', None)
        if highlights and isinstance(highlights, dict):
            return [f"{key}: {value}" for key, value in highlights.items()]
        return highlights

    def get_model(self, obj):
        return obj.__class__.__name__

def parse_query_block(field, expr, allowed_fields, field_types=None):
    # Normalize for metadata JSONField access
    if "." in field:
        lookup_field = "metadata__" + "__".join(field.split("."))
    else:
        lookup_field = field

    if lookup_field not in allowed_fields:
        raise ValueError(f"Invalid field: {field}")

    expected_type = None
    if field_types:
        expected_type = field_types.get(field)

    def validate_type(value, expected):
        if expected == "string" and not isinstance(value, str): return False
        if expected == "integer" and not isinstance(value, int): return False
        if expected == "number" and not isinstance(value, (int, float)): return False
        if expected == "boolean" and not isinstance(value, bool): return False
        if expected == "array" and not isinstance(value, list): return False
        if expected == "object" and not isinstance(value, dict): return False
        return True

    q = Q()
    for op, val in expr.items():
        if expected_type and not validate_type(val, expected_type):
            raise ValueError(f"Type mismatch for field '{field}': expected {expected_type}, got {type(val).__name__}")
        if op == "$eq":
            q &= Q(**{lookup_field: val})
        elif op == "$ne":
            q &= ~Q(**{lookup_field: val})
        elif op in ["$gt", "$gte", "$lt", "$lte", "$contains"]:
            q &= Q(**{f"{lookup_field}__{op[1:]}": val})
        elif op == "$regex":
            q &= Q(**{f"{lookup_field}__icontains": val})
        elif op == "$in":
            if not isinstance(val, list):
                raise ValueError(f"$in operator requires a list")
            q &= Q(**{f"{lookup_field}__in": val})
        elif op == "$nin":
            if not isinstance(val, list):
                raise ValueError(f"$nin operator requires a list")
            q &= ~Q(**{f"{lookup_field}__in": val})
        elif op == "$null":
            if not isinstance(val, bool):
                raise ValueError(f"$null operator requires a boolean")
            q &= Q(**{f"{lookup_field}__isnull": val})
        else:
            raise ValueError(f"Unsupported operator: {op}")

    return q

def parse_filter_tree(filters, allowed_fields, field_types=None):
    if isinstance(filters, dict):
        if "$and" in filters:
            return Q(*(parse_filter_tree(f, allowed_fields, field_types) for f in filters["$and"]))
        elif "$or" in filters:
            q = Q()
            for f in filters["$or"]:
                q |= parse_filter_tree(f, allowed_fields, field_types)
            return q
        elif "$not" in filters:
            return ~parse_filter_tree(filters["$not"], allowed_fields, field_types)

        q = Q()
        for field, expr in filters.items():
            if field.startswith("$"):
                raise ValueError(f"Invalid logical operator '{field}' at this level")
            if not isinstance(expr, dict):
                expr = {"$eq": expr}
            q &= parse_query_block(field, expr, allowed_fields, field_types)
        return q

    raise ValueError("Filters must be a dictionary")

def flatten_schema_properties(properties, path=""):
    keys = []
    for key, val in properties.items():
        full_key = f"{path}.{key}" if path else key
        keys.append(f"{full_key}")
        if val.get("type") == "object" and "properties" in val:
            keys.extend(flatten_schema_properties(val["properties"], full_key))
    return keys

def get_trigram_fields(model_class):
    """Return only safe CharField/TextField fields explicitly allowed in the model."""
    declared = set(getattr(model_class, 'trigram_search_fields', []))
    actual = {
        f.name for f in model_class._meta.get_fields()
        if isinstance(f, (CharField, TextField))
    }
    return list(declared & actual)

def collect_highlights(obj, filters, query, trigram_fields):
    highlights = {}

    for key in filters:
        normalized_key = key.replace(".", " → ")
        if key.startswith("metadata."):
            parts = key.split(".")[1:]
            value = getattr(obj, "metadata", {})
            for part in parts:
                value = value.get(part, None)
                if value is None:
                    break
            if value is not None:
                highlights[normalized_key] = value
        elif hasattr(obj, key):
            highlights[normalized_key] = getattr(obj, key)

    if query:
        for field in trigram_fields:
            val = getattr(obj, field, None)
            if isinstance(val, str) and query.lower() in val.lower():
                highlights[field] = val

    return highlights

class GeneralSearchViewSet(ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = GenericSearchPagination

    def create(self, request):
        from api.models import Schema

        query = request.data.get("q")
        filters = request.data.get("filters", {})
        schema_id = request.data.get("schema")
        model_name = request.data.get("model")

        models_to_search = [model_name] if model_name else [
            m.__name__ for m in apps.get_models() if m._meta.app_label == "api"
        ]

        results = []
        for name in models_to_search:
            try:
                model_class = apps.get_model("api", name)
                trigram_fields = get_trigram_fields(model_class)

                if query and not trigram_fields and not filters:
                    continue
            except LookupError:
                continue

            base_qs = get_objects_for_user(request.user, f"api.view_{name.lower()}", klass=model_class)

            allowed_fields = list(model_class._meta.fields_map.keys()) + [f.name for f in model_class._meta.fields]

            if schema_id:
                try:
                    schema_obj = Schema.objects.get(id=schema_id)
                    metadata_schema = schema_obj.schema.get("properties", {})
                    metadata_fields = flatten_schema_properties(metadata_schema)
                    field_types = {}
                    def flatten_schema_types(properties, path=""):
                        for key, val in properties.items():
                            full_key = f"{path}.{key}" if path else key
                            if val.get("type") == "object" and "properties" in val:
                                flatten_schema_types(val["properties"], full_key)
                            else:
                                field_types[full_key] = val.get("type")
                    flatten_schema_types(metadata_schema)
                    orm_fields = ["metadata__" + f.replace(".", "__") for f in metadata_fields]
                    allowed_fields += orm_fields
                except Schema.DoesNotExist:
                    continue
            print(f"Searching in model: {name} with allowed fields: {allowed_fields}", flush=True)

            # Handle filters
            q = Q()
            if filters:
                print(f"Applying filters: {filters}", flush=True)
                try:
                    q = parse_filter_tree(filters, allowed_fields, field_types if schema_id else None)
                except ValueError as e:
                    return Response({"error": str(e)}, status=400)
                
            print(f"Parsed query: {q}", flush=True)

            if query and trigram_fields:
                annotations = {
                    f"sim_{field}": TrigramSimilarity(
                        Cast(Coalesce(F(field), Value("")), output_field=TextField()),
                        Cast(Value(query), output_field=TextField())
                    )
                    for field in trigram_fields
                }
                if annotations:
                    base_qs = base_qs.annotate(**annotations)
                    if len(annotations) >= 2:
                        base_qs = base_qs.annotate(similarity=Greatest(*annotations.values(), output_field=FloatField()))
                    else:
                        field_expr = next(iter(annotations.values()))
                        base_qs = base_qs.annotate(similarity=Coalesce(field_expr, Value(0.0), output_field=FloatField()))
                    base_qs = base_qs.filter(similarity__gt=0.1).order_by("-similarity")

            qs = base_qs.filter(q).distinct()

            for obj in qs:
                obj._matched_fields = collect_highlights(obj, filters, query, trigram_fields)
                results.append(obj)

        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(results, request)

        if results:
            GenericSearchResultSerializer.Meta.model = results[0].__class__
        serializer = GenericSearchResultSerializer(paginated, many=True)
        return paginator.get_paginated_response(serializer.data)
