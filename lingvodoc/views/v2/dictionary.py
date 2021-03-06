__author__ = 'alexander'

from lingvodoc.exceptions import CommonException
from lingvodoc.models import (
    BaseGroup,
    Client,
    DBSession,
    Dictionary,
    DictionaryPerspective,
    Group,
    Language,
    LexicalEntry,
    Organization,
    User,
    TranslationAtom,
    TranslationGist
)

from lingvodoc.views.v2.utils import (
    all_languages,
    cache_clients,
    check_for_client,
    get_user_by_client_id,
    group_by_languages,
    group_by_organizations,
    user_counter
)

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPFound,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPOk
)
from pyramid.renderers import render_to_response
from pyramid.request import Request
from pyramid.response import Response
from pyramid.security import authenticated_userid
from pyramid.view import view_config

import sqlalchemy
from sqlalchemy import (
    func,
    and_
)
from sqlalchemy.exc import IntegrityError

import datetime
import json


@view_config(route_name='create_dictionary', renderer='json', request_method='POST', permission='create')
def create_dictionary(request):  # tested & in docs
    try:

        variables = {'auth': request.authenticated_userid}

        if type(request.json_body) == str:
            req = json.loads(request.json_body)
        else:
            req = request.json_body
        parent_client_id = req['parent_client_id']
        parent_object_id = req['parent_object_id']
        translation_gist_client_id = req['translation_gist_client_id']
        translation_gist_object_id = req['translation_gist_object_id']
        client = DBSession.query(Client).filter_by(id=variables['auth']).first()
        if not client:
            raise KeyError("Invalid client id (not registered on server). Try to logout and then login.")
        user = DBSession.query(User).filter_by(id=client.user_id).first()
        if not user:
            raise CommonException("This client id is orphaned. Try to logout and then login once more.")
        parent = DBSession.query(Language).filter_by(client_id=parent_client_id, object_id=parent_object_id).first()
        additional_metadata = req.get('additional_metadata')
        if additional_metadata:
            additional_metadata = json.dumps(additional_metadata)

        subreq = Request.blank('/translation_service_search')
        subreq.method = 'POST'
        subreq.headers = request.headers
        subreq.json = json.dumps({'searchstring': 'WiP'})
        headers = {'Cookie': request.headers['Cookie']}
        subreq.headers = headers
        resp = request.invoke_subrequest(subreq)

        if 'error' not in resp.json:
            state_translation_gist_object_id, state_translation_gist_client_id = resp.json['object_id'], resp.json['client_id']
        else:
            raise KeyError("Something wrong with the base", resp.json['error'])

        dictionary = Dictionary(client_id=variables['auth'],
                                state_translation_gist_object_id=state_translation_gist_object_id,
                                state_translation_gist_client_id=state_translation_gist_client_id,
                                parent=parent,
                                translation_gist_client_id=translation_gist_client_id,
                                translation_gist_object_id=translation_gist_object_id,
                                additional_metadata=additional_metadata)
        DBSession.add(dictionary)
        DBSession.flush()
        for base in DBSession.query(BaseGroup).filter_by(dictionary_default=True):
            new_group = Group(parent=base,
                              subject_object_id=dictionary.object_id, subject_client_id=dictionary.client_id)
            if user not in new_group.users:
                new_group.users.append(user)
            DBSession.add(new_group)
            DBSession.flush()
        request.response.status = HTTPOk.code
        return {'object_id': dictionary.object_id,
                'client_id': dictionary.client_id}
    except KeyError as e:
        request.response.status = HTTPBadRequest.code
        return {'error': str(e)}

    except IntegrityError as e:
        request.response.status = HTTPInternalServerError.code
        return {'error': str(e)}

    except CommonException as e:
        request.response.status = HTTPConflict.code
        return {'error': str(e)}


@view_config(route_name='dictionary', renderer='json', request_method='GET')  # Authors -- names of users, who can edit?
def view_dictionary(request):  # tested & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary and not dictionary.marked_for_deletion:
        response['parent_client_id'] = dictionary.parent_client_id
        response['parent_object_id'] = dictionary.parent_object_id
        response['translation_gist_client_id'] = dictionary.translation_gist_client_id
        response['translation_gist_object_id'] = dictionary.translation_gist_object_id
        response['client_id'] = dictionary.client_id
        response['object_id'] = dictionary.object_id
        response['state_translation_gist_client_id'] = dictionary.state_translation_gist_client_id
        response['state_translation_gist_object_id'] = dictionary.state_translation_gist_object_id
        response['additional_metadata'] = dictionary.additional_metadata
        response['translation'] = dictionary.get_translation(request.cookies['locale_id'])
        request.response.status = HTTPOk.code
        return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary', renderer='json', request_method='PUT', permission='edit')
def edit_dictionary(request):  # tested & in docs
    try:
        response = dict()
        client_id = request.matchdict.get('client_id')
        object_id = request.matchdict.get('object_id')
        client = DBSession.query(Client).filter_by(id=request.authenticated_userid).first()
        if not client:
            raise KeyError("Invalid client id (not registered on server). Try to logout and then login.")
        dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
        if dictionary:
            if not dictionary.marked_for_deletion:
                req = request.json_body
                if 'parent_client_id' in req:
                    dictionary.parent_client_id = req['parent_client_id']
                if 'parent_object_id' in req:
                    dictionary.parent_object_id = req['parent_object_id']
                if 'translation_gist_client_id' in req:
                    dictionary.translation_gist_client_id = req['translation_gist_client_id']
                if 'translation_gist_object_id' in req:
                    dictionary.translation_gist_object_id = req['translation_gist_object_id']

                additional_metadata = req.get('additional_metadata')
                if additional_metadata:
                    # additional_metadata = json.dumps(additional_metadata)

                    old_meta = json.loads(dictionary.additional_metadata)
                    old_meta.update(additional_metadata)
                    new_meta = json.dumps(old_meta)
                    dictionary.additional_metadata = new_meta
                request.response.status = HTTPOk.code
                return response
        request.response.status = HTTPNotFound.code
        return {'error': str("No such dictionary in the system")}
    except KeyError as e:
        request.response.status = HTTPBadRequest.code
        return {'error': str(e)}


@view_config(route_name='dictionary', renderer='json', request_method='DELETE', permission='delete')
def delete_dictionary(request):  # tested & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary:
        if not dictionary.marked_for_deletion:
            dictionary.marked_for_deletion = True
            request.response.status = HTTPOk.code
            return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


# TODO: completely broken!
@view_config(route_name='dictionary_copy', renderer='json', request_method='POST', permission='edit')
def copy_dictionary(request):
    response = dict()
    parent_client_id = request.matchdict.get('client_id')
    parent_object_id = request.matchdict.get('object_id')
    parent = DBSession.query(Dictionary).filter_by(client_id=parent_client_id, object_id=parent_object_id).first()
    if parent:
        path = request.route_url('create_dictionary')
        subreq = Request.blank(path)
        subreq.method = 'POST'
        subreq.json = json.dumps({'translation_gist_client_id': parent.translation_gist_client_id,
                                  'translation_gist_object_id': parent.translation_gist_object_id,
                                  'parent_client_id': parent.parent_client_id,
                                  'parent_object_id': parent.parent_object_id})
        headers = {'Cookie': request.headers['Cookie']}
        subreq.headers = headers
        resp = request.invoke_subrequest(subreq)
        new_dict = DBSession.query(Dictionary) \
            .filter_by(client_id=resp.json['client_id'], object_id=resp.json['object_id']) \
            .first()
        if parent.marked_for_deletion:
            new_dict.marked_for_deletion = True

        path = request.route_url('dictionary_roles',
                                 client_id=parent.client_id,
                                 object_id=parent.object_id)
        subreq = Request.blank(path)
        subreq.method = 'GET'
        headers = {'Cookie': request.headers['Cookie']}

        subreq.headers = headers
        resp = request.invoke_subrequest(subreq)
        path = request.route_url('dictionary_roles',
                                 client_id=new_dict.client_id,
                                 object_id=new_dict.object_id)
        subreq = Request.blank(path)
        subreq.method = 'POST'
        subreq.json = json.dumps(resp.json)
        headers = {'Cookie': request.headers['Cookie']}
        subreq.headers = headers
        resp = request.invoke_subrequest(subreq)
        path = request.route_url('dictionary_status',
                                 client_id=parent.client_id,
                                 object_id=parent.object_id)
        subreq = Request.blank(path)
        subreq.method = 'GET'
        headers = {'Cookie': request.headers['Cookie']}

        subreq.headers = headers
        resp = request.invoke_subrequest(subreq)
        path = request.route_url('dictionary_status',
                                 client_id=new_dict.client_id,
                                 object_id=new_dict.object_id)
        subreq = Request.blank(path)
        subreq.method = 'PUT'
        subreq.json = json.dumps(resp.json)
        headers = {'Cookie': request.headers['Cookie']}
        subreq.headers = headers
        resp = request.invoke_subrequest(subreq)

        perspectives = DBSession.query(DictionaryPerspective).filter_by(parent=parent)
        for perspective in perspectives:
            path = request.route_url('create_perspective',
                                     dictionary_client_id=new_dict.client_id,
                                     dictionary_object_id=new_dict.object_id)
            subreq = Request.blank(path)
            subreq.method = 'POST'
            subreq.json = json.dumps({'translation_gist_client_id': parent.translation_gist_client_id,
                                  'translation_gist_object_id': parent.translation_gist_object_id})
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)
            new_persp = DBSession.query(DictionaryPerspective) \
                .filter_by(client_id=resp.json['client_id'], object_id=resp.json['object_id']) \
                .first()

            if perspective.marked_for_deletion:
                new_persp.marked_for_deletion = True

            path = request.route_url('perspective_fields',
                                     dictionary_client_id=parent.client_id,
                                     dictionary_object_id=parent.object_id,
                                     perspective_client_id=perspective.client_id,
                                     perspective_id=perspective.object_id)
            subreq = Request.blank(path)
            subreq.method = 'GET'
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            path = request.route_url('perspective_fields',
                                     dictionary_client_id=new_dict.client_id,
                                     dictionary_object_id=new_dict.object_id,
                                     perspective_client_id=new_persp.client_id,
                                     perspective_id=new_persp.object_id)
            subreq = Request.blank(path)
            subreq.method = 'POST'
            subreq.json = json.dumps(resp.json)
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            path = request.route_url('perspective_status',
                                     dictionary_client_id=parent.client_id,
                                     dictionary_object_id=parent.object_id,
                                     perspective_client_id=perspective.client_id,
                                     perspective_id=perspective.object_id)
            subreq = Request.blank(path)
            subreq.method = 'GET'
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            path = request.route_url('perspective_status',
                                     dictionary_client_id=new_dict.client_id,
                                     dictionary_object_id=new_dict.object_id,
                                     perspective_client_id=new_persp.client_id,
                                     perspective_id=new_persp.object_id)
            subreq = Request.blank(path)
            subreq.method = 'PUT'
            subreq.json = json.dumps(resp.json)
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            path = request.route_url('perspective_roles',
                                     client_id=parent.client_id,
                                     object_id=parent.object_id,
                                     perspective_client_id=perspective.client_id,
                                     perspective_id=perspective.object_id)
            subreq = Request.blank(path)
            subreq.method = 'GET'
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            path = request.route_url('perspective_roles',
                                     client_id=new_dict.client_id,
                                     object_id=new_dict.object_id,
                                     perspective_client_id=new_persp.client_id,
                                     perspective_id=new_persp.object_id)
            subreq = Request.blank(path)
            subreq.method = 'POST'
            subreq.json = json.dumps(resp.json)
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            lexes = DBSession.query(LexicalEntry).filter_by(parent=perspective)
            for lex in lexes:
                new_lex = LexicalEntry(
                    object_id=DBSession.query(LexicalEntry).filter_by(client_id=lex.client_id).count() + 1,
                    client_id=lex.client_id,
                    parent=new_persp,
                    marked_for_deletion=lex.marked_for_deletion,
                    additional_metadata=lex.additional_metadata,
                    moved_to=lex.moved_to)  # if moved_to in this dict, should it be moved to in new dict?
                DBSession.add(new_lex)
                DBSession.flush()

                # l1es = DBSession.query(LevelOneEntity).filter_by(parent=lex)
                l1es = None
                for l1e in l1es:
                    # new_l1e = LevelOneEntity(client_id=l1e.client_id,
                    #                          object_id=DBSession.query(LevelOneEntity).filter_by(
                    #                              client_id=l1e.client_id).count() + 1,
                    #                          content=l1e.content,
                    #                          entity_type=l1e.entity_type,
                    #                          locale_id=l1e.locale_id,
                    #                          additional_metadata=l1e.additional_metadata,
                    #                          parent=new_lex,
                    #                          marked_for_deletion=l1e.marked_for_deletion,
                    #                          is_translatable=l1e.is_translatable,
                    #                          created_at=l1e.created_at)
                    new_l1e = None
                    DBSession.add(new_l1e)
                    DBSession.add(new_l1e)
                    DBSession.flush()
                    for pl1e in l1e.publishleveloneentity:
                        # new_pl1e = PublishLevelOneEntity(client_id=pl1e.client_id,
                        #                                  object_id=DBSession.query(PublishLevelOneEntity).filter_by(
                        #                                      client_id=pl1e.client_id).count() + 1,
                        #                                  content=pl1e.content,
                        #                                  entity_type=pl1e.entity_type,
                        #                                  parent=new_lex,
                        #                                  entity=new_l1e,
                        #                                  marked_for_deletion=pl1e.marked_for_deletion,
                        #                                  created_at=pl1e.created_at)
                        new_pl1e = None
                        DBSession.add(new_pl1e)
                        DBSession.flush()

                    # l2es = DBSession.query(LevelTwoEntity).filter_by(parent=l1e)
                    l2es = list()
                    for l2e in l2es:
                        # new_l2e = LevelTwoEntity(client_id=l2e.client_id,
                        #                          object_id=DBSession.query(LevelTwoEntity).filter_by(
                        #                              client_id=l2e.client_id).count() + 1,
                        #                          content=l2e.content,
                        #                          entity_type=l2e.entity_type,
                        #                          locale_id=l2e.locale_id,
                        #                          additional_metadata=l2e.additional_metadata,
                        #                          parent=new_l1e,
                        #                          marked_for_deletion=l2e.marked_for_deletion,
                        #                          is_translatable=l2e.is_translatable,
                        #                          created_at=l2e.created_at)
                        new_l2e = None
                        DBSession.add(new_l2e)
                        DBSession.flush()
                        for pl2e in l2e.publishleveltwoentity:
                            # new_pl2e = PublishLevelTwoEntity(client_id=pl2e.client_id,
                            #                                  object_id=DBSession.query(PublishLevelTwoEntity).filter_by(
                            #                                      client_id=pl2e.client_id).count() + 1,
                            #                                  content=pl2e.content,
                            #                                  entity_type=pl2e.entity_type,
                            #                                  parent=new_lex,
                            #                                  entity=new_l2e,
                            #                                  marked_for_deletion=pl2e.marked_for_deletion,
                            #                                  created_at=pl2e.created_at)
                            new_pl2e = None
                            DBSession.add(new_pl2e)
                            DBSession.flush()
                # ges = DBSession.query(GroupingEntity).filter_by(parent=lex)
                ges = list()
                for ge in ges:
                    # new_ge = GroupingEntity(client_id=ge.client_id,
                    #                         object_id=DBSession.query(GroupingEntity).filter_by(
                    #                             client_id=ge.client_id).count() + 1,
                    #                         content=ge.content,  # same tag?
                    #                         entity_type=ge.entity_type,
                    #                         locale_id=ge.locale_id,
                    #                         additional_metadata=ge.additional_metadata,
                    #                         parent=new_lex,
                    #                         marked_for_deletion=ge.marked_for_deletion,
                    #                         is_translatable=ge.is_translatable,
                    #                         created_at=ge.created_at)
                    new_ge = None
                    DBSession.add(new_ge)
                    DBSession.flush()
                    for pge in ge.publishgroupingentity:
                        # new_pge = PublishGroupingEntity(client_id=pge.client_id,
                        #                                 object_id=DBSession.query(PublishGroupingEntity).filter_by(
                        #                                     client_id=pge.client_id).count() + 1,
                        #                                 content=pge.content,
                        #                                 entity_type=pge.entity_type,
                        #                                 parent=new_lex,
                        #                                 entity=new_ge,
                        #                                 marked_for_deletion=pge.marked_for_deletion,
                        #                                 created_at=pge.created_at)
                        new_pge = None
                        DBSession.add(new_pge)
                        DBSession.flush()
        request.response.status = HTTPOk.code
        return {'client_id': new_dict.client_id,
                'object_id': new_dict.object_id}
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary_info', renderer='json', request_method='GET')
def dictionary_info(request):  # TODO: test
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    starting_date = request.GET.get('starting_date')
    if starting_date:
        starting_date = datetime.datetime(starting_date)
    ending_date = request.GET.get('ending_date')
    if ending_date:
        ending_date = datetime.datetime(ending_date)
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary:
        if not dictionary.marked_for_deletion:
            clients_to_users_dict = cache_clients()
            # todo: in one iteration

            types = []
            result = []
            for perspective in dictionary.dictionaryperspective:
                path = request.route_url('perspective_fields',
                                         dictionary_client_id=perspective.parent_client_id,
                                         dictionary_object_id=perspective.parent_object_id,
                                         perspective_client_id=perspective.client_id,
                                         perspective_id=perspective.object_id
                                         )
                subreq = Request.blank(path)
                subreq.method = 'GET'
                subreq.headers = request.headers
                resp = request.invoke_subrequest(subreq)
                fields = resp.json["fields"]
                for field in fields:
                    entity_type = field['entity_type']
                    if entity_type not in types:
                        types.append(entity_type)
                    if 'contains' in field:
                        for field2 in field['contains']:
                            entity_type = field2['entity_type']
                            if entity_type not in types:
                                types.append(entity_type)

            for perspective in dictionary.dictionaryperspective:
                for lex in perspective.lexicalentry:
                    result = user_counter(lex.track(True), result, starting_date, ending_date, types,
                                          clients_to_users_dict)

            response['count'] = result
            request.response.status = HTTPOk.code
            return response

    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


# TODO: completely broken!
@view_config(route_name='dictionary_delete', renderer='json', request_method='DELETE', permission='delete')
def real_delete_dictionary(request):
    response = dict()
    parent_client_id = request.matchdict.get('client_id')
    parent_object_id = request.matchdict.get('object_id')
    parent = DBSession.query(Dictionary).filter_by(client_id=parent_client_id, object_id=parent_object_id).first()
    if parent:
        perspectives = DBSession.query(DictionaryPerspective).filter_by(parent=parent)
        for perspective in perspectives:
            # fields = DBSession.query(DictionaryPerspectiveField).filter_by(parent=perspective).delete()
            fields = list()
            lexes = DBSession.query(LexicalEntry).filter_by(parent=perspective)
            for lex in lexes:
                # l1es = DBSession.query(LevelOneEntity).filter_by(parent=lex)
                l1es = list()
                for l1e in l1es:
                    # l2es = DBSession.query(LevelTwoEntity).filter_by(parent=l1e)
                    l2es = list()
                    for l2e in l2es:
                        # pl2es = DBSession.query(PublishLevelTwoEntity).filter_by(entity=l2e).delete()
                        pl2es = list()
                        DBSession.delete(l2e)
                    # pl1es = DBSession.query(PublishLevelOneEntity).filter_by(entity=l1e).delete()
                    pl1es = list()
                    DBSession.delete(l1e)
                # ges = DBSession.query(GroupingEntity).filter_by(parent=lex)
                ges = list()
                for ge in ges:
                    # pges = DBSession.query(PublishGroupingEntity).filter_by(entity=ge).delete()
                    pges = list()
                    DBSession.delete(ge)
                DBSession.delete(lex)
            for base in DBSession.query(BaseGroup).filter_by(perspective_default=True):
                groups = DBSession.query(Group).filter_by(parent=base,
                                                          subject_client_id=perspective.client_id,
                                                          subject_object_id=perspective.object_id).all()
                for group in groups:
                    users = []
                    for user in group.users:
                        users.append(user)
                    for user in users:
                        group.users.remove(user)
                    DBSession.delete(group)

            DBSession.delete(perspective)
        for base in DBSession.query(BaseGroup).filter_by(dictionary_default=True):
            groups = DBSession.query(Group).filter_by(parent=base,
                                                      subject_client_id=parent.client_id,
                                                      subject_object_id=parent.object_id).all()
            for group in groups:
                users = []
                for user in group.users:
                    users.append(user)
                for user in users:
                    group.users.remove(user)
                DBSession.delete(group)
        DBSession.delete(parent)
        request.response.status = HTTPOk.code
        return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary_roles', renderer='json', request_method='GET', permission='view')
def view_dictionary_roles(request):  # tested & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary:
        if not dictionary.marked_for_deletion:
            bases = DBSession.query(BaseGroup).filter_by(dictionary_default=True)
            roles_users = dict()
            roles_organizations = dict()
            for base in bases:
                group = DBSession.query(Group).filter_by(base_group_id=base.id,
                                                         subject_object_id=object_id,
                                                         subject_client_id=client_id).first()
                perm = base.name
                users = []
                for user in group.users:
                    users += [user.id]
                organizations = []
                for org in group.organizations:
                    organizations += [org.id]
                roles_users[perm] = users
                roles_organizations[perm] = organizations
            response['roles_users'] = roles_users
            response['roles_organizations'] = roles_organizations

            request.response.status = HTTPOk.code
            return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary_roles', renderer='json', request_method='POST', permission='create')
def edit_dictionary_roles(request):  # tested & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')

    if type(request.json_body) == str:
        req = json.loads(request.json_body)
    else:
        req = request.json_body
    roles_users = None
    if 'roles_users' in req:
        roles_users = req['roles_users']
    roles_organizations = None
    if 'roles_organizations' in req:
        roles_organizations = req['roles_organizations']
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary:
        if not dictionary.marked_for_deletion:
            if roles_users:
                for role_name in roles_users:
                    base = DBSession.query(BaseGroup).filter_by(name=role_name,
                                                                dictionary_default=True).first()
                    if not base:
                        request.response.status = HTTPNotFound.code
                        return {'error': str("No such role in the system")}

                    group = DBSession.query(Group).filter_by(base_group_id=base.id,
                                                             subject_object_id=object_id,
                                                             subject_client_id=client_id).first()

                    client = DBSession.query(Client).filter_by(id=request.authenticated_userid).first()

                    userlogged = DBSession.query(User).filter_by(id=client.user_id).first()

                    permitted = False
                    if userlogged in group.users:
                        permitted = True
                    if not permitted:
                        for org in userlogged.organizations:
                            if org in group.organizations:
                                permitted = True
                                break

                    if permitted:
                        users = roles_users[role_name]
                        for userid in users:
                            user = DBSession.query(User).filter_by(id=userid).first()
                            if user:
                                if user not in group.users:
                                    group.users.append(user)
                    else:
                        request.response.status = HTTPForbidden.code
                        return {'error': str("Not enough permission")}

            if roles_organizations:
                for role_name in roles_organizations:
                    base = DBSession.query(BaseGroup).filter_by(name=role_name,
                                                                dictionary_default=True).first()
                    if not base:
                        request.response.status = HTTPNotFound.code
                        return {'error': str("No such role in the system")}

                    group = DBSession.query(Group).filter_by(base_group_id=base.id,
                                                             subject_object_id=object_id,
                                                             subject_client_id=client_id).first()

                    client = DBSession.query(Client).filter_by(id=request.authenticated_userid).first()

                    userlogged = DBSession.query(User).filter_by(id=client.user_id).first()

                    permitted = False
                    if userlogged in group.users:
                        permitted = True
                    if not permitted:
                        for org in userlogged.organizations:
                            if org in group.organizations:
                                permitted = True
                                break

                    if permitted:
                        orgs = roles_organizations[role_name]
                        for orgid in orgs:
                            org = DBSession.query(Organization).filter_by(id=orgid).first()
                            if org:
                                if org not in group.organizations:
                                    group.organizations.append(org)
                    else:
                        request.response.status = HTTPForbidden.code
                        return {'error': str("Not enough permission")}

            request.response.status = HTTPOk.code
            return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary_roles', renderer='json', request_method='DELETE', permission='delete')
def delete_dictionary_roles(request):  # & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    req = request.json_body
    roles_users = None
    if 'roles_users' in req:
        roles_users = req['roles_users']
    roles_organizations = None
    if 'roles_organizations' in req:
        roles_organizations = req['roles_organizations']
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary:
        if not dictionary.marked_for_deletion:
            if roles_users:
                for role_name in roles_users:
                    base = DBSession.query(BaseGroup).filter_by(name=role_name,
                                                                dictionary_default=True).first()
                    if not base:
                        request.response.status = HTTPNotFound.code
                        return {'error': str("No such role in the system")}

                    group = DBSession.query(Group).filter_by(base_group_id=base.id,
                                                             subject_object_id=object_id,
                                                             subject_client_id=client_id).first()

                    client = DBSession.query(Client).filter_by(id=request.authenticated_userid).first()

                    userlogged = DBSession.query(User).filter_by(id=client.user_id).first()

                    permitted = False
                    if userlogged in group.users:
                        permitted = True
                    if not permitted:
                        for org in userlogged.organizations:
                            if org in group.organizations:
                                permitted = True
                                break

                    if permitted:
                        users = roles_users[role_name]
                        for userid in users:
                            user = DBSession.query(User).filter_by(id=userid).first()
                            if user:
                                if user.id == userlogged.id:
                                    request.response.status = HTTPForbidden.code
                                    return {'error': str("Cannot delete roles from self")}
                                if user in group.users:
                                    group.users.remove(user)
                    else:
                        request.response.status = HTTPForbidden.code
                        return {'error': str("Not enough permission")}

            if roles_organizations:
                for role_name in roles_organizations:
                    base = DBSession.query(BaseGroup).filter_by(name=role_name,
                                                                dictionary_default=True).first()
                    if not base:
                        request.response.status = HTTPNotFound.code
                        return {'error': str("No such role in the system")}

                    group = DBSession.query(Group).filter_by(base_group_id=base.id,
                                                             subject_object_id=object_id,
                                                             subject_client_id=client_id).first()

                    client = DBSession.query(Client).filter_by(id=request.authenticated_userid).first()

                    userlogged = DBSession.query(User).filter_by(id=client.user_id).first()

                    permitted = False
                    if userlogged in group.users:
                        permitted = True
                    if not permitted:
                        for org in userlogged.organizations:
                            if org in group.organizations:
                                permitted = True
                                break

                    if permitted:
                        orgs = roles_organizations[role_name]
                        for orgid in orgs:
                            org = DBSession.query(Organization).filter_by(id=orgid).first()
                            if org:
                                if org in group.organizations:
                                    group.organizations.remove(org)
                    else:
                        request.response.status = HTTPForbidden.code
                        return {'error': str("Not enough permission")}

            request.response.status = HTTPOk.code
            return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary_status', renderer='json', request_method='GET')
def view_dictionary_status(request):  # tested & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary and not dictionary.marked_for_deletion:
        response['state_translation_gist_client_id'] = dictionary.state_translation_gist_client_id
        response['state_translation_gist_object_id'] = dictionary.state_translation_gist_object_id
        atom = DBSession.query(TranslationAtom).filter_by(parent_client_id=dictionary.state_translation_gist_client_id,
                                                          parent_object_id=dictionary.state_translation_gist_object_id,
                                                          locale_id=int(request.cookies['locale_id'])).first()
        response['status'] = atom.content
        request.response.status = HTTPOk.code
        return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionary_status', renderer='json', request_method='PUT', permission='edit')
def edit_dictionary_status(request):  # tested & in docs
    response = dict()
    client_id = request.matchdict.get('client_id')
    object_id = request.matchdict.get('object_id')
    dictionary = DBSession.query(Dictionary).filter_by(client_id=client_id, object_id=object_id).first()
    if dictionary and not dictionary.marked_for_deletion:
        if type(request.json_body) == str:
            req = json.loads(request.json_body)
        else:
            req = request.json_body
        dictionary.state_translation_gist_client_id = req['state_translation_gist_client_id']
        dictionary.state_translation_gist_object_id = req['state_translation_gist_object_id']
        atom = DBSession.query(TranslationAtom).filter_by(parent_client_id=req['state_translation_gist_client_id'],
                                                          parent_object_id=req['state_translation_gist_object_id'],
                                                          locale_id=int(request.cookies['locale_id'])).first()
        response['status'] = atom.content
        request.response.status = HTTPOk.code
        return response
    request.response.status = HTTPNotFound.code
    return {'error': str("No such dictionary in the system")}


@view_config(route_name='dictionaries', renderer='json', request_method='POST')
def dictionaries_list(request):  # TODO: test
    req = request.json_body
    response = dict()
    user_created = None
    if 'user_created' in req:
        user_created = req['user_created']
    author = None
    if 'author' in req:
        author = req['author']
    published = None
    if 'published' in req:
        published = req['published']
    user_participated = None
    if 'user_participated' in req:
        user_participated = req['user_participated']
    organization_participated = None
    if 'organization_participated' in req:
        organization_participated = req['organization_participated']
    languages = None
    if 'languages' in req:
        languages = req['languages']
    dicts = DBSession.query(Dictionary).filter(Dictionary.marked_for_deletion == False)
    if published:
        if published:
            subreq = Request.blank('/translation_service_search')
            subreq.method = 'POST'
            subreq.headers = request.headers
            subreq.json = json.dumps({'searchstring': 'WiP'})
            headers = {'Cookie': request.headers['Cookie']}
            subreq.headers = headers
            resp = request.invoke_subrequest(subreq)

            if 'error' not in resp.json:
                state_translation_gist_object_id, state_translation_gist_client_id = resp.json['object_id'], resp.json['client_id']
            else:
                raise KeyError("Something wrong with the base", resp.json['error'])
            dicts = dicts.filter(and_(Dictionary.state_translation_gist_object_id == state_translation_gist_object_id, Dictionary.state_translation_gist_client_id == state_translation_gist_client_id)).join(DictionaryPerspective) \
                .filter(and_(Dictionary.state_translation_gist_object_id == state_translation_gist_object_id, Dictionary.state_translation_gist_client_id == state_translation_gist_client_id))
    if user_created:
        clients = DBSession.query(Client).filter(Client.user_id.in_(user_created)).all()
        cli = [o.id for o in clients]
        response['clients'] = cli
        dicts = dicts.filter(Dictionary.client_id.in_(cli))

    if languages:
        langs = []
        for lan in languages:
            lang = DBSession.query(Language).filter_by(object_id=lan['object_id'], client_id=lan['client_id']).first()
            langs += all_languages(lang)

        if langs:
            prevdicts = DBSession.query(Dictionary).filter(sqlalchemy.sql.false())
            for lan in langs:
                prevdicts = prevdicts.subquery().select()
                prevdicts = dicts.filter_by(parent_client_id=lan['client_id'],
                                            parent_object_id=lan['object_id']).union_all(prevdicts)

            dicts = prevdicts
        else:
            dicts = DBSession.query(Dictionary).filter(sqlalchemy.sql.false())

    # add geo coordinates
    if organization_participated:
        organization = DBSession.query(Organization).filter(Organization.id.in_(organization_participated)).first()
        users = organization.users
        users_id = [o.id for o in users]

        clients = DBSession.query(Client).filter(Client.user_id.in_(users_id)).all()
        cli = [o.id for o in clients]

        dictstemp = []
        for dicti in dicts:
            if check_for_client(dicti, cli):
                dictstemp += [{'client_id': dicti.client_id, 'object_id': dicti.object_id}]
        if dictstemp:
            prevdicts = DBSession.query(Dictionary).filter(sqlalchemy.sql.false())
            for dicti in dictstemp:
                prevdicts = prevdicts.subquery().select()
                prevdicts = dicts.filter_by(client_id=dicti['client_id'], object_id=dicti['object_id']).union_all(
                    prevdicts)

            dicts = prevdicts
        else:
            dicts = DBSession.query(Dictionary).filter(sqlalchemy.sql.false())

    if user_participated:
        clients = DBSession.query(Client).filter(Client.user_id.in_(user_participated)).all()
        cli = [o.id for o in clients]

        dictstemp = []
        for dicti in dicts:
            if check_for_client(dicti, cli):
                dictstemp += [{'client_id': dicti.client_id, 'object_id': dicti.object_id}]
        if dictstemp:
            prevdicts = DBSession.query(Dictionary).filter(sqlalchemy.sql.false())
            for dicti in dictstemp:
                prevdicts = prevdicts.subquery().select()
                prevdicts = dicts.filter_by(client_id=dicti['client_id'], object_id=dicti['object_id']).union_all(
                    prevdicts)

            dicts = prevdicts
        else:
            dicts = DBSession.query(Dictionary).filter(sqlalchemy.sql.false())
    # TODO: fix.
    # TODO: start writing todos with more information

    dictionaries = list()
    dicts = dicts.order_by(Dictionary.client_id, Dictionary.object_id)
    for dct in dicts:
        path = request.route_url('dictionary',
                                 client_id=dct.client_id,
                                 object_id=dct.object_id)
        subreq = Request.blank(path)
        subreq.method = 'GET'
        subreq.headers = request.headers
        resp = request.invoke_subrequest(subreq)
        if 'error' not in resp.json:
            dictionaries += [resp.json]
    # return {'count': dicts.count()}

    if author:
        user = DBSession.query(User).filter_by(id=author).first()
        dictstemp = []  # [{'client_id': dicti.client_id, 'object_id': dicti.object_id}]
        isadmin = False
        for group in user.groups:
            if group.parent.dictionary_default:
                if group.subject_override:
                    isadmin = True
                    break
                dcttmp = (group.subject_client_id, group.subject_object_id)
                if dcttmp not in dictstemp:
                    dictstemp += [dcttmp]
            if group.parent.perspective_default:
                if group.subject_override:
                    isadmin = True
                    break
                dicti = DBSession.query(Dictionary) \
                    .join(DictionaryPerspective) \
                    .filter_by(client_id=group.subject_client_id,
                               object_id=group.subject_object_id) \
                    .first()
                if dicti:
                    dcttmp = (dicti.client_id, dicti.object_id)
                    if dcttmp not in dictstemp:
                        dictstemp += [dcttmp]
        if not isadmin:
            dictionaries = [o for o in dictionaries if (o['client_id'], o['object_id']) in dictstemp]
    response['dictionaries'] = dictionaries
    request.response.status = HTTPOk.code

    return response


@view_config(route_name='published_dictionaries', renderer='json', request_method='POST')
def published_dictionaries_list(request):  # tested.   # TODO: test with org
    req = request.json_body
    response = dict()
    group_by_org = None
    if 'group_by_org' in req:
        group_by_org = req['group_by_org']
    group_by_lang = None
    if 'group_by_lang' in req:
        group_by_lang = req['group_by_lang']
    dicts = DBSession.query(Dictionary)

    subreq = Request.blank('/translation_service_search')
    subreq.method = 'POST'
    subreq.headers = request.headers
    subreq.json = json.dumps({'searchstring': 'WiP'})
    headers = {'Cookie': request.headers['Cookie']}
    subreq.headers = headers
    resp = request.invoke_subrequest(subreq)

    if 'error' not in resp.json:
        state_translation_gist_object_id, state_translation_gist_client_id = resp.json['object_id'], resp.json['client_id']
    else:
        raise KeyError("Something wrong with the base", resp.json['error'])
    dicts = dicts.filter(and_(Dictionary.state_translation_gist_object_id == state_translation_gist_object_id, Dictionary.state_translation_gist_client_id == state_translation_gist_client_id)).join(DictionaryPerspective) \
        .filter(and_(Dictionary.state_translation_gist_object_id == state_translation_gist_object_id, Dictionary.state_translation_gist_client_id == state_translation_gist_client_id))

    if group_by_lang and not group_by_org:
        return group_by_languages(dicts, request)

    if not group_by_lang and group_by_org:
        tmp = group_by_organizations(dicts, request)
        organizations = []
        for org in tmp:
            dcts = org['dicts']
            dictionaries = []
            for dct in dcts:
                path = request.route_url('dictionary',
                                         client_id=dct.client_id,
                                         object_id=dct.object_id)
                subreq = Request.blank(path)
                subreq.method = 'GET'
                subreq.headers = request.headers
                resp = request.invoke_subrequest(subreq)
                if 'error' not in resp.json:
                    dictionaries += [resp.json]
            org['dicts'] = dictionaries
            organizations += [org]
        return {'organizations': organizations}
    if group_by_lang and group_by_org:
        tmp = group_by_organizations(dicts, request)
        organizations = []
        for org in tmp:
            dcts = org['dicts']
            org['langs'] = group_by_languages(dcts, request)
            del org['dicts']
            organizations += [org]
        return {'organizations': organizations}
    dictionaries = []
    dicts = dicts.order_by("client_id", "object_id")
    for dct in dicts:
        path = request.route_url('dictionary',
                                 client_id=dct.client_id,
                                 object_id=dct.object_id)
        subreq = Request.blank(path)
        subreq.method = 'GET'
        subreq.headers = request.headers
        resp = request.invoke_subrequest(subreq)
        if 'error' not in resp.json:
            dictionaries += [resp.json]
    response['dictionaries'] = dictionaries
    request.response.status = HTTPOk.code

    return response


@view_config(route_name='new_dictionary', renderer='templates/create_dictionary.pt', request_method='GET')
def new_dictionary_get(request):
    client_id = authenticated_userid(request)
    user = get_user_by_client_id(client_id)
    if user is None:
        response = Response()
        return HTTPFound(location=request.route_url('login'), headers=response.headers)
    variables = {'client_id': client_id, 'user': user}
    return render_to_response('templates/create_dictionary.pt', variables, request=request)
