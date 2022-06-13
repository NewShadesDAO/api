from pymongo import ASCENDING
from umongo import fields

from app.helpers.db_utils import instance
from app.models.base import APIDocument


@instance.register
class User(APIDocument):
    display_name = fields.StrField()
    wallet_address = fields.StrField()
    ens_domain = fields.StrField()
    email = fields.StrField()
    pfp = fields.DictField()
    description = fields.StrField()
    online_channels = fields.ListField(fields.StrField(), required=False, default=[])
    status = fields.StrField(default="offline")

    class Meta:
        collection_name = "users"
        indexes = [[("wallet_address", ASCENDING), {"unique": True}]]


@instance.register
class Role(APIDocument):
    server = fields.ReferenceField("Server")

    name = fields.StrField()
    permissions = fields.ListField(fields.StrField)

    class Meta:
        collection_name = "roles"
        indexes = ["server"]
