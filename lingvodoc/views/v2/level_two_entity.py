__author__ = 'alexander'

from lingvodoc.exceptions import CommonException
from lingvodoc.views.v2.utils import (
    create_object
)
from lingvodoc.models import (
    Client,
    DBSession,
    User
)

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPOk
)
from pyramid.security import authenticated_userid
from pyramid.view import view_config

from sqlalchemy.exc import IntegrityError

import base64
import hashlib
import json


# TODO: Completely broken!
@view_config(route_name='get_level_two_entity_indict', renderer='json', request_method='GET', permission='view')
@view_config(route_name='get_level_two_entity', renderer='json', request_method='GET', permission='view')
def view_l2_entity(request):
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    # entity = DBSession.query(LevelTwoEntity).filter_by(client_id=client_id, object_id=object_id).first()
    entity = None
    if entity:
        if not entity.marked_for_deletion:
            # TODO: use track
            response['entity_type'] = entity.entity_type
            response['parent_client_id'] = entity.parent_client_id
            response['parent_object_id'] = entity.parent_object_id
            response['content'] = entity.content
            response['locale_id'] = entity.locale_id
            request.response.status = HTTPOk.code
            return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such entity in the system")}


# TODO: completely broken!
@view_config(route_name='create_level_two_entity', renderer='json', request_method='POST', permission='create')
def create_l2_entity(request):
    try:

        variables = {'auth': authenticated_userid(request)}
        response = dict()
        parent_client_id = request.matchdict.get('level_one_client_id')
        parent_object_id = request.matchdict.get('level_one_object_id')
        req = request.json_body
        client = DBSession.query(Client).filter_by(id=variables['auth']).first()
        if not client:
            raise KeyError("Invalid client id (not registered on server). Try to logout and then login.")
        user = DBSession.query(User).filter_by(id=client.user_id).first()
        if not user:
            raise CommonException("This client id is orphaned. Try to logout and then login once more.")

        # parent = DBSession.query(LevelOneEntity).filter_by(client_id=parent_client_id, object_id=parent_object_id).first()
        parent = None
        if not parent:
            request.response.status = HTTPNotFound.code
            return {'error': str("No such level one entity in the system")}
        additional_metadata = req.get('additional_metadata')
        # entity = LevelTwoEntity(client_id=client.id, object_id=DBSession.query(LevelTwoEntity).filter_by(client_id=client.id).count() + 1, entity_type=req['entity_type'],
        #                         locale_id=req['locale_id'], additional_metadata=additional_metadata,
        #                         parent=parent)
        entity = None

        DBSession.add(entity)
        DBSession.flush()
        data_type = req.get('data_type')
        filename = req.get('filename')
        real_location = None
        url = None
        if data_type == 'image' or data_type == 'sound' or data_type == 'markup':
            real_location, url = create_object(request, req['content'], entity, data_type, filename)

        if url and real_location:
            entity.content = url
            old_meta = entity.additional_metadata

            need_hash = True
            if old_meta:
                new_meta=json.loads(old_meta)
                if new_meta.get('hash'):
                    need_hash = False
            if need_hash:
                hash = hashlib.sha224(base64.urlsafe_b64decode(req['content'])).hexdigest()
                hash_dict = {'hash': hash}
                if old_meta:
                    new_meta = json.loads(old_meta)
                    new_meta.update(hash_dict)
                else:
                    new_meta = hash_dict
                entity.additional_metadata = json.dumps(new_meta)
        else:
            entity.content = req['content']
        DBSession.add(entity)
        request.response.status = HTTPOk.code
        response['client_id'] = entity.client_id
        response['object_id'] = entity.object_id
        return response
    except KeyError as e:
        request.response.status = HTTPBadRequest.code
        return {'error': str(e)}

    except IntegrityError as e:
        request.response.status = HTTPInternalServerError.code
        return {'error': str(e)}

    except CommonException as e:
        request.response.status = HTTPConflict.code
        return {'error': str(e)}


# TODO: completely broken!
@view_config(route_name='get_level_two_entity_indict', renderer='json', request_method='DELETE', permission='delete')
@view_config(route_name='get_level_two_entity', renderer='json', request_method='DELETE', permission='delete')
def delete_l2_entity(request):
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')

    # entity = DBSession.query(LevelTwoEntity).filter_by(client_id=client_id, object_id=object_id).first()
    entity = None
    if entity:
        if not entity.marked_for_deletion:

            entity.marked_for_deletion = True
            request.response.status = HTTPOk.code
            return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such entity in the system")}