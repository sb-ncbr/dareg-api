from rest_framework import permissions
from .models import Project, Facility

def max_perm(obj, request, current_perm="none"):

    lowercaseClassName = obj.__class__.__name__.lower()

    higher_level = {
        "dataset": Project,
        "project": Facility,
        "facility": None
    }

    for x in ["owner", "editor", "viewer"]:
        
        if x == current_perm:
            break
        
        if request.user.has_perm(lowercaseClassName + "_" + x, obj):
            current_perm = x
            break
    
    upper_obj = higher_level[lowercaseClassName]
    
    if not upper_obj:
        return current_perm
    
    obj = getattr(obj, upper_obj.__name__.lower())
    
    return max_perm(obj, request, current_perm)


class NestedPerms(permissions.BasePermission):

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):

        perm_level = {
            "owner": 3,
            "editor": 2,
            "viewer": 1,
            "none": 0
        }
        
        match request.method:
            case "GET":
                required_perm = "viewer"
            case "POST":
                required_perm = "editor"
            case "PUT":
                required_perm = "editor"
            case "PATCH":
                required_perm = "editor"
            case "DELETE":
                required_perm = "owner"
            case "OPTIONS":
                required_perm = "viewer"
                
        return perm_level[max_perm(obj, request)] >= perm_level[required_perm]

