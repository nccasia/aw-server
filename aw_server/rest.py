from functools import wraps
from types import MethodType
from typing import Dict
import traceback
import json
import re

from flask import redirect, request, Blueprint, jsonify, current_app, make_response, session
from flask_restx import Api, Resource, fields
import iso8601

from aw_core import schema
from aw_core.models import Event
from aw_query.exceptions import QueryException

from . import logger
from .api import ServerAPI
from .exceptions import BadRequest, Unauthorized

from .config import config

import time
import base64

import http.client
import urllib.parse
import os

from dotenv import load_dotenv
load_dotenv()
X_SECRET_KEY = os.getenv('X_SECRET_KEY')

oauth2_auth_url = config["oauth2"]["auth_url"]
oauth2_client_id = config["oauth2"]["client_id"]
oauth2_client_secret = config["oauth2"]["client_secret"]
oauth2_redirect_uri = config["oauth2"]["redirect_uri"]
application_domain = config["server"]["application_domain"]

def current_milli_time():
    return round(time.time() * 1000)

def base64_encode(message):
    message_bytes = message.encode('ascii')
    base64_bytes = base64.b64encode(message_bytes)
    base64_message = base64_bytes.decode('ascii')
    return base64_message
    
def base64_decode(base64_message):
    try:
        base64_bytes = base64_message.encode('ascii')
        message_bytes = base64.b64decode(base64_bytes)
        message = message_bytes.decode('ascii')
    except:
        message = None
        
    return message

def host_header_check(f):
    """
    Protects against DNS rebinding attacks (see https://github.com/nccasia/komutracker/security/advisories/GHSA-v9fg-6g9j-h4x4)

    Some discussion in Syncthing how they do it: https://github.com/syncthing/syncthing/issues/4819
    """

    @wraps(f)
    def decorator(*args, **kwargs):
        # TODO: What if server is bound to 0.0.0.0?
        server_host = current_app.config["HOST"]
        req_host = request.headers.get("host", None)
        req_secret = request.headers.get("secret", None)

        millisec = int(base64_decode(req_secret) or 0)
        
        if current_milli_time() - millisec > 15000 and request.method != "GET":
            return {"message": "bad request"}, 400

        if req_host is None:
            return {"message": "host header is missing"}, 400
        else:
            if req_host.split(":")[0] not in ["localhost", "127.0.0.1", application_domain, server_host]:
                return {"message": f"host header is invalid (was {req_host})"}, 400
        
    return decorator

def authentication_check(f):
    """
    Check authenticated user
    """

    @wraps(f)
    def decorator(*args, **kwargs):
        origin = request.environ.get('HTTP_ORIGIN', '')
        device_id = request.headers.get("device_id", None)
        secret = request.headers.get("secret", None)
        xSecret = request.headers.get('X-Secret-Key', 'None')
        if re.search("DESKTOP", request.path):
            logger.info(f"ip address: {request.remote_addr}")
            logger.info(f"Device Id: {device_id}")
            return {"message": "bad request"}, 400  
        if origin == f"http://{application_domain}" or \
            origin == f"https://{application_domain}" or \
            origin == "http://localhost:27180" or \
            (re.search("auth/callback", request.path) is not None) or \
            (re.search("auth", request.path) is not None and request.method == "POST") or \
            xSecret == X_SECRET_KEY or \
            secret is not None:
            return f(*args, **kwargs)

        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]   
            user = current_app.api.get_user_by_token(device_id,auth_header.replace("Bearer ", ""))
            if user is None:
                return {"message": "not authenticated"}, 401
            # logger.info(f"Current User: {user.get('email'), user.get('device_id')}")
            if '_id' in user:
                del user['_id']
            session['user'] = user
            return f(*args, **kwargs)
        else:
            return {"message": "authorization header needed"}, 400 

    return decorator

def make_mezon_oauth2_request(method:str, path:str, params: dict):
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    prepared_params = urllib.parse.urlencode({
        'client_id': oauth2_client_id,
        'client_secret': oauth2_client_secret,
        'redirect_uri': oauth2_redirect_uri,
        **params
    })
    conn = http.client.HTTPSConnection(oauth2_auth_url)
    conn.request(
        method,
        path,
        body=prepared_params,
        headers=headers
    )
    response = conn.getresponse()
    if response.status != 200:
        print(f"Error: {response.status}")
        print(response.read())
        return None
    return json.loads(response.read())   

blueprint = Blueprint("api", __name__, url_prefix="/api")
api = Api(blueprint, doc="/", decorators=[authentication_check])
# api = Api(blueprint, doc="/")

class AnyJson(fields.Raw):
    def format(self, value):
        if type(value) == dict:
            return value
        else:
            return json.loads(value)


# Loads event and bucket schema from JSONSchema in aw_core
event = api.schema_model("Event", schema.get_json_schema("event"))
bucket = api.schema_model("Bucket", schema.get_json_schema("bucket"))
buckets_export = api.schema_model("Export", schema.get_json_schema("export"))

# TODO: Construct all the models from JSONSchema?
#       A downside to contructing from JSONSchema: flask-restplus does not have marshalling support

info = api.model(
    "Info",
    {
        "hostname": fields.String(),
        "version": fields.String(),
        "testing": fields.Boolean(),
        "device_id": fields.String(),
    },
)

create_bucket = api.model(
    "CreateBucket",
    {
        "client": fields.String(required=True),
        "type": fields.String(required=True),
        "hostname": fields.String(required=True),
    },
)

query = api.model(
    "Query",
    {
        "timeperiods": fields.List(
            fields.String, required=True, description="List of periods to query"
        ),
        "query": fields.List(
            fields.String, required=True, description="String list of query statements"
        ),
    },
)


def copy_doc(api_method):
    """Decorator that copies another functions docstring to the decorated function.
    Used to copy the docstrings in ServerAPI over to the flask-restplus Resources.
    (The copied docstrings are then used by flask-restplus/swagger)"""

    def decorator(f):
        f.__doc__ = api_method.__doc__
        return f

    return decorator


# SERVER INFO


@api.route("/0/info")
class InfoResource(Resource):
    @api.marshal_with(info)
    @copy_doc(ServerAPI.get_info)
    def get(self) -> Dict[str, Dict]:
        return current_app.api.get_info()


# BUCKETS


@api.route("/0/buckets/")
class BucketsResource(Resource):
    # TODO: Add response marshalling/validation
    @copy_doc(ServerAPI.get_buckets)
    def get(self) -> Dict[str, Dict]:
        return current_app.api.get_buckets()


@api.route("/0/buckets/<string:bucket_id>")
class BucketResource(Resource):
    @api.doc(model=bucket)
    @copy_doc(ServerAPI.get_bucket_metadata)
    def get(self, bucket_id):
        return current_app.api.get_bucket_metadata(bucket_id)

    @api.expect(create_bucket)
    @copy_doc(ServerAPI.create_bucket)
    def post(self, bucket_id):
        logger.info(bucket_id)
        data = request.get_json()
        bucket_created = current_app.api.create_bucket(
            bucket_id,
            event_type=data["type"],
            client=data["client"],
            hostname=data["hostname"],
        )
        if bucket_created:
            return {}, 200
        else:
            return {}, 304

    @copy_doc(ServerAPI.delete_bucket)
    @api.param("force", "Needs to be =1 to delete a bucket it non-testing mode")
    def delete(self, bucket_id):
        args = request.args
        if not current_app.api.testing:
            if "force" not in args or args["force"] != "1":
                msg = "Deleting buckets is only permitted if aw-server is running in testing mode or if ?force=1"
                raise Unauthorized("DeleteBucketUnauthorized", msg)

        current_app.api.delete_bucket(bucket_id)
        return {}, 200


# EVENTS


@api.route("/0/buckets/<string:bucket_id>/events")
class EventsResource(Resource):
    # For some reason this doesn't work with the JSONSchema variant
    # Marshalling doesn't work with JSONSchema events
    # @api.marshal_list_with(event)
    @api.doc(model=event)
    @api.param("limit", "the maximum number of requests to get")
    @api.param("start", "Start date of events")
    @api.param("end", "End date of events")
    @copy_doc(ServerAPI.get_events)
    def get(self, bucket_id):
        args = request.args
        limit = int(args["limit"]) if "limit" in args else -1
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        events = current_app.api.get_events(
            bucket_id, limit=limit, start=start, end=end
        )
        return events, 200

    # TODO: How to tell expect that it could be a list of events? Until then we can't use validate.
    @api.expect(event)
    @copy_doc(ServerAPI.create_events)
    def post(self, bucket_id):
        data = request.get_json()
        logger.debug(
            "Received post request for event in bucket '{}' and data: {}".format(
                bucket_id, data
            )
        )

        if isinstance(data, dict):
            events = [Event(**data)]
        elif isinstance(data, list):
            events = [Event(**e) for e in data]
        else:
            raise BadRequest("Invalid POST data", "")

        event = current_app.api.create_events(bucket_id, events)
        return event.to_json_dict() if event else None, 200


@api.route("/0/buckets/<string:bucket_id>/events/count")
class EventCountResource(Resource):
    @api.doc(model=fields.Integer)
    @api.param("start", "Start date of eventcount")
    @api.param("end", "End date of eventcount")
    @copy_doc(ServerAPI.get_eventcount)
    def get(self, bucket_id):
        args = request.args
        start = iso8601.parse_date(args["start"]) if "start" in args else None
        end = iso8601.parse_date(args["end"]) if "end" in args else None

        events = current_app.api.get_eventcount(bucket_id, start=start, end=end)
        return events, 200


@api.route("/0/buckets/<string:bucket_id>/events/<int:event_id>")
class EventResource(Resource):
    @api.doc(model=event)
    @copy_doc(ServerAPI.get_event)
    def get(self, bucket_id: str, event_id: int):
        logger.debug(
            f"Received get request for event with id '{event_id}' in bucket '{bucket_id}'"
        )
        event = current_app.api.get_event(bucket_id, event_id)
        if event:
            return event, 200
        else:
            return None, 404

    @copy_doc(ServerAPI.delete_event)
    def delete(self, bucket_id: str, event_id: int):
        logger.debug(
            "Received delete request for event with id '{}' in bucket '{}'".format(
                event_id, bucket_id
            )
        )
        success = current_app.api.delete_event(bucket_id, event_id)
        return {"success": success}, 200


@api.route("/0/buckets/<string:bucket_id>/heartbeat")
class HeartbeatResource(Resource):
    @api.expect(event, validate=True)
    @api.param(
        "pulsetime", "Largest timewindow allowed between heartbeats for them to merge"
    )
    @copy_doc(ServerAPI.heartbeat)
    def post(self, bucket_id):
        heartbeat = Event(**request.get_json())
        logger.debug(
            f"Received heartbeat in bucket '{bucket_id}'"
        )
        if "pulsetime" in request.args:
            pulsetime = float(request.args["pulsetime"])
        else:
            raise BadRequest("MissingParameter", "Missing required parameter pulsetime")

        event = current_app.api.heartbeat(bucket_id, heartbeat, pulsetime)
        event.id = str(event.id)
        return event.to_json_dict(), 200


# QUERY


@api.route("/0/query/")
class QueryResource(Resource):
    # TODO Docs
    @api.expect(query, validate=True)
    @api.param("name", "Name of the query (required if using cache)")
    def post(self):
        name = ""
        if "name" in request.args:
            name = request.args["name"]
        query = request.get_json()
        try:
            result = current_app.api.query2(
                name, query["query"], query["timeperiods"], False
            )
            return jsonify(result)
        except QueryException as qe:
            traceback.print_exc()
            return {"type": type(qe).__name__, "message": str(qe)}, 400


# EXPORT AND IMPORT


@api.route("/0/export")
class ExportAllResource(Resource):
    @api.doc(model=buckets_export)
    @copy_doc(ServerAPI.export_all)
    def get(self):
        buckets_export = current_app.api.export_all()
        payload = {"buckets": buckets_export}
        response = make_response(json.dumps(payload))
        filename = "aw-buckets-export.json"
        response.headers["Content-Disposition"] = "attachment; filename={}".format(
            filename
        )
        return response


# TODO: Perhaps we don't need this, could be done with a query argument to /0/export instead
@api.route("/0/buckets/<string:bucket_id>/export")
class BucketExportResource(Resource):
    @api.doc(model=buckets_export)
    @copy_doc(ServerAPI.export_bucket)
    def get(self, bucket_id):
        bucket_export = current_app.api.export_bucket(bucket_id)
        payload = {"buckets": {bucket_export["id"]: bucket_export}}
        response = make_response(json.dumps(payload))
        filename = "aw-bucket-export_{}.json".format(bucket_export["id"])
        response.headers["Content-Disposition"] = "attachment; filename={}".format(
            filename
        )
        return response


@api.route("/0/import")
class ImportAllResource(Resource):
    @api.expect(buckets_export)
    @copy_doc(ServerAPI.import_all)
    def post(self):
        # If import comes from a form in th web-ui
        if len(request.files) > 0:
            # web-ui form only allows one file, but technically it's possible to
            # upload multiple files at the same time
            for filename, f in request.files.items():
                buckets = json.loads(f.stream.read())["buckets"]
                current_app.api.import_all(buckets)
        # Normal import from body
        else:
            buckets = request.get_json()["buckets"]
            current_app.api.import_all(buckets)
        return None, 200


# LOGGING


@api.route("/0/log")
class LogResource(Resource):
    @copy_doc(ServerAPI.get_log)
    def get(self):
        return current_app.api.get_log(), 200


# AUTH

@api.route("/0/auth")
class AuthResource(Resource):
    def post(self):
        data = request.get_json()
        token = current_app.api.get_user_token(data["device_id"])
        # logger.info(f"get token for device: {data['device_id']}")
        return token

@api.route("/0/auth/me")
class AuthResource(Resource):
    def get(self):
        return session['user']

@api.route("/0/auth/callback")
class AuthCallbackResource(Resource):
    def get(self):
        device_id = request.args["state"]
        logger.info(f"Auth callback for device: {device_id}")
        data = make_mezon_oauth2_request(
            method = "POST", 
            path = "/oauth2/token", 
            params = {
                'grant_type': 'authorization_code',
                'code': request.args["code"],
                'scope': '',
            }
        )
        if data is None:
            return
        token = data["access_token"]
        user = make_mezon_oauth2_request(
            method = "POST", 
            path = "/userinfo", 
            params = {
                'access_token': token,
            }
        )
        user_email = user["sub"]
        logger.info(f"Auth success for: {user_email}")
        
        current_app.api.save_user({
            "device_id": device_id,
            "name": user_email,
            "email": user_email,
            "access_token": data["access_token"], 
            "refresh_token": data["access_token"]
        })
        
        user_name = re.split("@", user_email, 1)[0]
        
        return redirect(f"http://{application_domain}/#/activity/{user_name}/view/", code=302)

# REPORT

@api.route("/0/report/<string:email>")
class Report(Resource):
    def get(self, email):
        day = request.args.get("day")
        report = current_app.api.get_user_report(email, day)
        return report
@api.route("/0/report")
class ReportEmployeesOnDate(Resource):
    def post(self):
        day = request.args.get("day")
        req = request.get_json()
        if "emails" in req:
            emails = req["emails"]
        else:
            raise BadRequest("MissingParameter", "Missing required parameter emails") 
        logger.info(f"Reporting emails on date {day}")
        res = []
        for email in emails:
            raw_report = current_app.api.get_user_report(email,day)
            raw_report.pop("spent_time", None)
            raw_report.pop("call_time", None)
            raw_report.pop("str_active_time", None)
            raw_report.pop("str_spent_time", None)
            raw_report.pop("str_call_time", None)
            raw_report.pop("date", None)
            raw_report.pop("wfh", None)
            res.append(raw_report)
        return res, 200
@api.route("/0/report")
class ReportAll(Resource):
    def get(self):
        day = request.args.get("day")
        response = current_app.api.report_all(day)
        return response
