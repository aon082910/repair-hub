from django import template
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.html import format_html

from ..models import Favorite

register = template.Library()


@register.simple_tag(takes_context=True)
def favorite_button(context, obj):
    request = context["request"]
    user = request.user
    content_type = ContentType.objects.get_for_model(obj)
    is_favorited = False
    if user.is_authenticated:
        is_favorited = Favorite.objects.filter(user=user, content_type=content_type, object_id=obj.pk).exists()
    label = "★ Favorited" if is_favorited else "☆ Favorite"
    return format_html(
        '<form method="post" action="{}" style="display:inline;">'
        '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
        '<input type="hidden" name="content_type_id" value="{}">'
        '<input type="hidden" name="object_id" value="{}">'
        '<input type="hidden" name="next" value="{}">'
        '<button type="submit" class="btn secondary" style="padding:0.35rem 0.7rem;">{}</button>'
        "</form>",
        reverse("toggle_favorite"),
        context.get("csrf_token", ""),
        content_type.pk,
        obj.pk,
        request.path,
        label,
    )
