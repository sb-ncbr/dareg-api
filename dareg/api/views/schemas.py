from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from guardian.shortcuts import get_perms
from api.models import Schema
from api.views.query import flatten_schema_properties

class SchemaMetadataFieldsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, schema_id):
        try:
            schema = Schema.objects.get(id=schema_id)

            # Check if user has the required permission directly
            if "view_schema" not in get_perms(request.user, schema):
                return Response({"error": "Permission denied"}, status=403)

            schema_dict = schema.schema
            if not isinstance(schema_dict, dict):
                return Response({"error": "Schema format invalid"}, status=400)

            properties = schema_dict.get("properties", {})
            metadata_fields = flatten_schema_properties(properties)

            return Response({
                "schema": f"{schema.name} (v{schema.version})",
                "fields": metadata_fields
            })

        except Schema.DoesNotExist:
            return Response({"error": "Schema not found"}, status=404)
