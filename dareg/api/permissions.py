from rest_framework import permissions
from .models import Project, Facility, PermsGroup, User

def update_perms(id, request):
    
    if request.data.get('shares'):
        
        for x in ["owner", "editor", "viewer"]:
            group = PermsGroup.objects.get(name=f"{id}_{x}")
            for user in group.user_set.all():
                group.user_set.remove(user)

        for x in request.data.get('shares'):
            group = PermsGroup.objects.get(name=f"{id}_{x['perms']}")
            user = User.objects.get(id=x["id"])
            group.user_set.add(user)

def max_perm(obj, request, current_perm="none", text_output=False):

    higher_level = {
        "dataset": Project,
        "project": Facility,
        "facility": None
    }

    perm_level = {
        "owner": 3,
        "editor": 2,
        "viewer": 1,
        "none": 0
    }

    for x in ["owner", "editor", "viewer"]:
        
        if x == current_perm:
            break
        
        if request.user.has_perm(x, obj):
            current_perm = x
            break
    
    upper_obj = higher_level[obj.__class__.__name__.lower()]
    
    if not upper_obj:
        return current_perm if text_output else perm_level[current_perm]
    
    obj = getattr(obj, upper_obj.__name__.lower())
    
    return max_perm(obj, request, current_perm, text_output)


class NestedPerms(permissions.BasePermission):

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        
        match request.method:
            case "GET":
                required_perm = 1
            case "POST":
                required_perm = 2
            case "PUT":
                required_perm = 2
            case "PATCH":
                required_perm = 2
            case "DELETE":
                required_perm = 3
            case "OPTIONS":
                required_perm = 1
                
        return max_perm(obj, request) >= required_perm

