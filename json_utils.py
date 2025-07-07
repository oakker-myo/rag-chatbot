import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)

def serialize_datetime_fields(data):
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = serialize_datetime_fields(value)
        return result
    elif isinstance(data, list):
        return [serialize_datetime_fields(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, UUID):
        return str(data)
    else:
        return data

def safe_json_response(data):
    return serialize_datetime_fields(data)