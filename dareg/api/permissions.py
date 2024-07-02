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


class NestedPerms(permissions.BasePermission):

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):

        match request.method:
            case "GET":
                required_perm = PermsGroup.VIEWER
            case "POST":
                required_perm = PermsGroup.EDITOR
            case "PUT":
                required_perm = PermsGroup.EDITOR
            case "PATCH":
                required_perm = PermsGroup.EDITOR
            case "DELETE":
                required_perm = PermsGroup.OWNER
            case "OPTIONS":
                required_perm = PermsGroup.VIEWER
                
        return obj.perm_atleast(request, required_perm)

class SameUser(permissions.BasePermission):

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user
    
