__author__ = 'alexander'

from lingvodoc.models import (
    Client,
    DBSession,
    Dictionary,
    Language,
    Organization,
    User,
    UserBlobs,
    TranslationAtom
)

from pyramid.request import Request

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import joinedload

import swiftclient.client as swiftclient

import datetime
import base64
import json
import os
import shutil

def cache_clients():
    clients_to_users_dict = dict()
    clients = DBSession.query(Client) \
        .options(joinedload('user')).all()
    for client in clients:
        clients_to_users_dict[client.id] = {'id': client.user.id,
                                            'login': client.user.login,
                                            'name': client.user.name,
                                            'intl_name': client.user.intl_name}
    return clients_to_users_dict


def check_for_client(obj, clients):
    if obj.client_id in clients:
        return True
    for entry in dir(obj):
        if entry in inspect(type(obj)).relationships:
            i = inspect(obj.__class__).relationships[entry]
            if i.direction.name == "ONETOMANY":
                x = getattr(obj, str(entry))
                answer = False
                for xx in x:
                    answer = answer or check_for_client(xx, clients)
                    if answer:
                        break
                return answer
    return False


def all_languages(lang):
    langs = [{'object_id': lang.object_id, 'client_id': lang.client_id}]
    for la in lang.language:
        langs += all_languages(la)
    return langs


# Json_input point to the method of file getting: if it's embedded in json, we need to decode it. If
# it's uploaded via multipart form, it's just saved as-is.
def create_object(request, content, obj, data_type, filename, json_input=True):
    import errno
    # here will be object storage write as an option. Fallback (default) is filesystem write
    settings = request.registry.settings
    storage = settings['storage']
    if storage['type'] == 'openstack':
        if json_input:
            content = base64.urlsafe_b64decode(content)
        # TODO: openstack objects correct naming
        filename = str(obj.data_type) + '/' + str(obj.client_id) + '_' + str(obj.object_id)
        real_location = openstack_upload(settings, content, filename, obj.data_type, 'test')
    else:
        filename = filename or 'noname.noext'
        storage_path, filename = object_file_path(obj, settings, data_type, filename, True)
        directory = os.path.dirname(storage_path)  # TODO: find out, why object_file_path were not creating dir
        try:
            os.makedirs(directory)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
        with open(storage_path, 'wb+') as f:
            if json_input:
                f.write(base64.urlsafe_b64decode(content))
            else:
                shutil.copyfileobj(content, f)

        real_location = storage_path

    url = "".join((settings['storage']['prefix'],
                  settings['storage']['static_route'],
                  obj.__tablename__,
                  '/',
                  data_type,
                  '/',
                  str(obj.client_id), '/',
                  str(obj.object_id), '/',
                  filename))
    return real_location, url


def get_user_by_client_id(client_id):
    user = None
    client = DBSession.query(Client).filter_by(id=client_id).first()
    if client is not None:
        user = DBSession.query(User).filter_by(id=client.user_id).first()
    return user


def group_by_languages(dicts, request):
    langs = DBSession.query(Language).filter_by(marked_for_deletion=False, parent=None).all()
    languages = []
    for lang in langs:
        la = language_with_dicts(lang, dicts, request)
        if la:
            languages += [la]
    return languages


def group_by_organizations(dicts, request):
        dicts_with_users = []
        for dct in dicts:
            users = []
            for client in participated_clients_list(dct, request):
                user = DBSession.query(User).join(Client).filter_by(id = client).first()
                if user not in users:
                    users += [user]
            dicts_with_users += [(dct.object_id, dct.client_id, users)]
        organizations = []
        for organization in DBSession.query(Organization).filter_by(marked_for_deletion=False).all():
            dictionaries = []
            for dct in dicts_with_users:
                for user in dct[2]:
                    if user in organization.users:
                        dictionaries += [dct]
            path = request.route_url('organization',
                 organization_id=organization.id)
            subreq = Request.blank(path)
            subreq.method = 'GET'
            subreq.headers = request.headers
            resp = request.invoke_subrequest(subreq)
            if 'error' not in resp.json:
                org = resp.json

                dictstemp = [{'client_id': o[1], 'object_id': o[0]} for o in dictionaries]
                dictionaries = dicts
                if dictstemp:
                    prevdicts = dictionaries\
                        .filter_by(client_id=dictstemp[0]['client_id'],
                                   object_id=dictstemp[0]['object_id'])
                    dictstemp.remove(dictstemp[0])
                    for dicti in dictstemp:
                        prevdicts = prevdicts.subquery().select()
                        prevdicts = dictionaries.filter_by(client_id=dicti['client_id'], object_id=dicti['object_id'])\
                            .union_all(prevdicts)

                    dictionaries = prevdicts

                org['dicts'] = dictionaries
                organizations += [org]
        return organizations


def language_info(lang, request):
    result = dict()
    result['client_id'] = lang.client_id
    result['object_id'] = lang.object_id
    result['translation_gist_client_id'] = lang.translation_gist_client_id
    result['translation_gist_object_id'] = lang.translation_gist_object_id
    if lang.locale:
        result['locale_exist'] = True
    else:
        result['locale_exist'] = False

    if lang.language:
        contains = []
        for childlang in lang.language:
            if childlang.marked_for_deletion:
                continue
            contains += [language_info(childlang, request)]
        result['contains'] = contains

    return result


def language_with_dicts(lang, dicts, request):
    result = dict()
    result['client_id'] = lang.client_id
    result['object_id'] = lang.object_id
    result['translation_gist_client_id'] = lang.translation_gist_client_id
    result['translation_gist_object_id'] = lang.translation_gist_object_id
    if lang.locale:
        result['locale_exist'] = True
    else:
        result['locale_exist'] = False
    dictionaries = []
    ds = dicts.filter((Dictionary.parent_client_id==lang.client_id) & (
                         Dictionary.parent_object_id==lang.object_id)).all()

    for dct in ds:
        path = request.route_url('dictionary',
                                 client_id=dct.client_id,
                                 object_id=dct.object_id)
        subreq = Request.blank(path)
        subreq.method = 'GET'
        subreq.headers = request.headers
        resp = request.invoke_subrequest(subreq)
        if 'error' not in resp.json:
            dictionaries += [resp.json]
    result['dicts'] = dictionaries

    contains = []
    if lang.language:
        for childlang in lang.language:
            ent = language_with_dicts(childlang, dicts, request)
            if ent:
                contains += [ent]
    result['contains'] = contains
    if not result['contains'] and not result['dicts']:
        return []
    if not result['contains']:
        del result['contains']
    return result



def object_file_path(obj, settings, data_type, filename, create_dir=False):
    from werkzeug.utils import secure_filename
    filename = secure_filename(filename)
    base_path = settings['storage']['path']
    storage_dir = os.path.join(base_path, obj.__tablename__, data_type, str(obj.client_id), str(obj.object_id))
    if create_dir:
        os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, filename)

    return storage_path, filename


def openstack_upload(settings, file, file_name, content_type,  container_name):
    storage = settings['storage']
    authurl = storage['authurl']
    user = storage['user']
    key = storage['key']
    auth_version = storage['auth_version']
    tenant_name = storage['tenant_name']
    conn = swiftclient.Connection(authurl=authurl, user=user, key=key,  auth_version=auth_version,
                                  tenant_name=tenant_name)
    #storageurl = conn.get_auth()[0]
    conn.put_container(container_name)
    obje = conn.put_object(container_name, file_name,
                    contents = file,
                    content_type = content_type)
    #obje = conn.get_object(container_name, file_name)
    return str(obje)


def participated_clients_list(dictionary, request):
    clients = [dictionary.client_id]
    for persp in dictionary.dictionaryperspective:
        if persp.state.lowercase() == 'published':
            path = request.route_url('lexical_entries_published',
                                     dictionary_client_id = dictionary.client_id,
                                     dictionary_object_id = dictionary.object_id,
                                     perspective_client_id = persp.client_id,
                                     perspective_id = persp.object_id)
            subreq = Request.blank(path)
            subreq.method = 'GET'
            subreq.headers = request.headers
            resp = request.invoke_subrequest(subreq)
            if not 'error' in resp.json:
                for entry in resp.json['lexical_entries']:
                    clients += participated_clients_rec(entry)
    return clients


def participated_clients_rec(entry):
    clients = []
    if entry:
        if 'level' in entry:
            if 'publish' not in entry['level']:
                clients += [entry['client_id']]
                if 'contains' in entry:
                    if entry['contains']:
                        for ent in entry['contains']:
                            clients += participated_clients_rec(ent)
    return clients


def remove_deleted(lst):
    entries = []
    if lst:
        for entry in lst:
            entries += [entry]
        for entry in entries:
            if entry['marked_for_deletion']:
                lst.remove(entry)
            else:
                if 'contains' in entry:
                    remove_deleted(entry['contains'])
    return



def user_counter(entry, result, starting_date, ending_date, types, clients_to_users_dict):
    empty = False
    if entry['level'] == 'lexicalentry':
        if 'contains' not in entry:
            empty = True
        elif not entry['contains']:
            empty = True
    if 'contains' in entry:
        if entry['contains']:
            for ent in entry['contains']:
                result = user_counter(ent, result, starting_date, ending_date, types, clients_to_users_dict)
    if 'created_at' in entry:
        if starting_date:
            if datetime.datetime(entry['created_at']).date() < starting_date:
                empty = True
        if ending_date:
            if datetime.datetime(entry['created_at']).date() > ending_date:
                empty = True
    if 'content' in entry:
        if not entry['content'] or entry['content'].isspace():
            empty = True

    if empty:
        return result

    user = clients_to_users_dict.get(entry['client_id'])
    if user:
        user_exist = next((item for item in result if item['id'] == user['id']), None)
        # user_exist = [item for item in result if item["id"] == user['id']]
        if not user_exist:
            counters = dict()
            for entity_type in types:
                counters[entity_type] = 0
            counters['lexical_entry'] = 0
            user['counters'] = counters
            result += [user]
            user_exist = user
        # else:
        #     user_exist = user_exist[0]
        user_count = user_exist['counters']
        if entry['level'] == 'lexicalentry':
            user_count['lexical_entry'] += 1
        else:
            if 'entity_type' in entry:
                user_count[entry['entity_type']] += 1
    return result


def view_perspective_from_object(request, perspective):
    response = dict()
    if perspective:
        if not perspective.marked_for_deletion:
            response['parent_client_id'] = perspective.parent_client_id
            response['parent_object_id'] = perspective.parent_object_id
            response['client_id'] = perspective.client_id
            response['object_id'] = perspective.object_id
            response['translation_gist_client_id'] = perspective.translation_gist_client_id
            response['translation_gist_object_id'] = perspective.translation_gist_object_id
            response['state_translation_gist_client_id'] = perspective.state_translation_gist_client_id
            response['state_translation_gist_object_id'] = perspective.state_translation_gist_object_id
            response['marked_for_deletion'] = perspective.marked_for_deletion
            response['is_template'] = perspective.is_template
            response['additional_metadata'] = perspective.additional_metadata
            response['translation'] = perspective.get_translation(request.cookies['locale_id'])
            if perspective.additional_metadata:
                meta = json.loads(perspective.additional_metadata)
                if 'location' in meta:
                    response['location'] = meta['location']
                if 'info' in meta:
                    response['info'] = meta['info']
                    remove_list = []
                    info_list = response['info']['content']
                    for info in info_list:
                        content = info['info']['content']
                        blob = DBSession.query(UserBlobs).filter_by(client_id=content['client_id'],
                                                                    object_id=content['object_id']).first()
                        if blob:
                            prevnamewaswrong = {'name': blob.name, 'content': blob.content, 'data_type': blob.data_type,
                                        'client_id': blob.client_id, 'object_id': blob.object_id}
                            info['info']['content'] = prevnamewaswrong
                        else:
                            if info not in remove_list:
                                remove_list.append(info)
            return response
    return {'error':'no persp'}


def view_field_from_object(request, field):
    response = dict()
    if field and not field.marked_for_deletion:
        response['client_id'] = field.client_id
        response['object_id'] = field.object_id
        response['created_at'] = str(field.created_at)
        response['data_type_translation_gist_client_id'] = field.data_type_translation_gist_client_id
        response['data_type_translation_gist_object_id'] = field.data_type_translation_gist_object_id
        response['translation'] = field.get_translation(request.cookies['locale_id'])
        response['is_translatable'] = field.is_translatable
        response['translation_gist_client_id'] = field.translation_gist_client_id
        response['translation_gist_object_id'] = field.translation_gist_object_id
        atom = DBSession.query(TranslationAtom).filter_by(parent_client_id=field.data_type_translation_gist_client_id,
                                                          parent_object_id=field.data_type_translation_gist_object_id,
                                                          locale_id=int(request.cookies['locale_id'])).first()
        if atom:
            response['data_type'] = atom.content
        else:
            print('no atom content for ids', field.data_type_translation_gist_client_id, field.data_type_translation_gist_object_id)
        return response
    return {'error': 'no field'}