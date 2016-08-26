# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging

from keystoneclient.v2_0 import client

from contrail_api_cli.command import Command, Arg, expand_paths
from contrail_api_cli.resource import Collection
from contrail_api_cli.utils import printo, parallel_map, FQName, continue_prompt
from contrail_api_cli.exceptions import ChildrenExists, BackRefsExists
from contrail_api_cli.client import HTTPError


logger = logging.getLogger(__name__)


class FindOrphanedProjects(Command):
    """Command to find projects that are still in contrail but no more in keystone.

    Run::

        contrail-api-cli find-orphaned-projects
    """

    description = "Find projects that are not in keystone"

    def _check(self, project):
        if project.fq_name == FQName('default-domain:default-project'):
            return
        keystone_uuid = project.uuid.replace('-', '')
        try:
            self.kclient.tenants.get(keystone_uuid)
        except HTTPError as e:
            if e.http_status == 404:
                printo(self.current_path(project))
            else:
                raise

    def __call__(self):
        self.kclient = client.Client(session=Collection.session)
        parallel_map(self._check, Collection('project', fetch=True),
                     workers=50)


class PurgeProject(Command):
    """Command to purge a project. All related resources are deleted.

    .. warning::

        This command is experimental and not fully tested.

    This command works recursively by first trying to remove
    the project. If other resources are linked to the project
    the API will return a 409 response with all linked resources.
    The command will then try to delete these resources and so
    on until the project resource can be deleted.

    Because of this no dry-run mode is possible.

    To run the command::

        contrail-api-cli --ns contrail_api_cli.clean purge-project project/uuid
    """

    description = "Purge contrail projects"
    paths = Arg(nargs="+", help="path(s)", metavar='path',
                complete="resources:project:path")

    def _handle_si_vm(self, iip, vmi):
        # to cleanup SI we need to remove manually the VMs
        # since the si -> vm ref is derived it won't trigger
        # a BackRefsExists error in the backend
        iip.fetch()
        for vmi in iip.get('virtual_machine_interface_refs', []):
            vmi.fetch()
            if 'virtual_machine_interface_properties' not in vmi:
                continue
            for vm in vmi.get('virtual_machine_refs', []):
                vm.fetch()
                for vm_vmi in vm.get('virtual_machine_interface_back_refs', []):
                    vm_vmi.remove_ref(vm)
                self._delete(vm)
        self._delete(iip)

    def _remove_back_ref(self, resource, parent):
        printo("remove back ref from %s to %s" %
               (self.current_path(parent), self.current_path(resource)))
        parent.remove_back_ref(resource)

    def _delete(self, resource, parent=None):
        try:
            logger.debug("trying to delete %s" % self.current_path(resource))
            resource.delete()
            printo("%s deleted" % self.current_path(resource))
        except (ChildrenExists, BackRefsExists) as e:
            action = self.actions[e.__class__].get(
                (resource.type, e.resources[0].type), self._delete)
            for r in e.resources:
                action(r, resource)
            self._delete(resource)

    def __call__(self, paths=None, **kwargs):
        super(PurgeProject, self).__call__(**kwargs)

        self.actions = {
            BackRefsExists: {
                ('virtual-machine', 'virtual-router'): self._remove_back_ref,
                ('virtual-machine-interface', 'instance-ip'): self._handle_si_vm
            },
            ChildrenExists: {}
        }

        resources = expand_paths(paths,
                                 predicate=lambda r: r.type == 'project')

        if not continue_prompt("Do you really want to purge theses projects ? All resources will be destroyed !"):
            return
        for project in resources:
            self._delete(project)
