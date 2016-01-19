# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from six import text_type
import json

from contrail_api_cli.commands import Command, Arg
from contrail_api_cli.resource import Resource, Collection
from contrail_api_cli.exceptions import CommandError


class SAS(Command):
    appliance_set_name = Arg(help='name')


class AddSAS(SAS):
    description = 'Add service appliance set'
    driver = Arg('--driver',
                 required=True,
                 help='driver python module path')

    def __call__(self, appliance_set_name=None, driver=None):
        global_config = Resource('global-system-config',
                                 fq_name='default-global-system-config',
                                 check_fq_name=True)
        sas = Resource('service-appliance-set',
                       fq_name='default-global-system-config:%s' % appliance_set_name)
        sas['parent_type'] = 'global-system-config'
        sas['parent_uuid'] = global_config.uuid
        sas['service_appliance_driver'] = driver
        sas.save()


class DelSAS(SAS):
    description = 'Del service appliance set'

    def __call__(self, appliance_set_name=None):
        try:
            sas = Resource('service-appliance-set',
                           fq_name='default-global-system-config:%s' % appliance_set_name,
                           check_fq_name=True)
            sas.delete()
        except ValueError as e:
            raise CommandError(text_type(e))


class ListSAS(Command):
    description = 'List service appliance sets'

    def __call__(self):
        sass = Collection('service-appliance-set',
                          fetch=True, recursive=2)
        return json.dumps([{'appliance_set_name': sas.fq_name[-1],
                            'driver': sas['service_appliance_driver']}
                          for sas in sass if 'service_appliance_driver' in sas], indent=2)
