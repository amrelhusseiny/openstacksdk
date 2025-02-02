# Copyright (c) 2015 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2016 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TODO(shade) The normalize functions here should get merged in to
#             the sdk resource objects.

import munch

from openstack import resource

_IMAGE_FIELDS = (
    'checksum',
    'container_format',
    'direct_url',
    'disk_format',
    'file',
    'id',
    'name',
    'owner',
    'virtual_size',
)

_SERVER_FIELDS = (
    'accessIPv4',
    'accessIPv6',
    'addresses',
    'adminPass',
    'created',
    'description',
    'key_name',
    'metadata',
    'networks',
    'personality',
    'private_v4',
    'public_v4',
    'public_v6',
    'server_groups',
    'status',
    'updated',
    'user_id',
    'tags',
)

_pushdown_fields = {
    'project': [
        'domain_id'
    ]
}


def _to_bool(value):
    if isinstance(value, str):
        if not value:
            return False
        prospective = value.lower().capitalize()
        return prospective == 'True'
    return bool(value)


def _pop_int(resource, key):
    return int(resource.pop(key, 0) or 0)


def _pop_or_get(resource, key, default, strict):
    if strict:
        return resource.pop(key, default)
    else:
        return resource.get(key, default)


class Normalizer:
    '''Mix-in class to provide the normalization functions.

    This is in a separate class just for on-disk source code organization
    reasons.
    '''

    def _remove_novaclient_artifacts(self, item):
        # Remove novaclient artifacts
        item.pop('links', None)
        item.pop('NAME_ATTR', None)
        item.pop('HUMAN_ID', None)
        item.pop('human_id', None)
        item.pop('request_ids', None)
        item.pop('x_openstack_request_ids', None)

    def _normalize_image(self, image):
        if isinstance(image, resource.Resource):
            image = image.to_dict(ignore_none=True, original_names=True)
            location = image.pop(
                'location',
                self._get_current_location(project_id=image.get('owner')))
        else:
            location = self._get_current_location(
                project_id=image.get('owner'))
            # This copy is to keep things from getting epically weird in tests
            image = image.copy()

        new_image = munch.Munch(location=location)

        # Discard noise
        self._remove_novaclient_artifacts(image)

        # If someone made a property called "properties" that contains a
        # string (this has happened at least one time in the wild), the
        # the rest of the normalization here goes belly up.
        properties = image.pop('properties', {})
        if not isinstance(properties, dict):
            properties = {'properties': properties}

        visibility = image.pop('visibility', None)
        protected = _to_bool(image.pop('protected', False))

        if visibility:
            is_public = (visibility == 'public')
        else:
            is_public = image.pop('is_public', False)
            visibility = 'public' if is_public else 'private'

        new_image['size'] = image.pop('OS-EXT-IMG-SIZE:size', 0)
        new_image['size'] = image.pop('size', new_image['size'])

        new_image['min_ram'] = image.pop('minRam', 0)
        new_image['min_ram'] = image.pop('min_ram', new_image['min_ram'])

        new_image['min_disk'] = image.pop('minDisk', 0)
        new_image['min_disk'] = image.pop('min_disk', new_image['min_disk'])

        new_image['created_at'] = image.pop('created', '')
        new_image['created_at'] = image.pop(
            'created_at', new_image['created_at'])

        new_image['updated_at'] = image.pop('updated', '')
        new_image['updated_at'] = image.pop(
            'updated_at', new_image['updated_at'])

        for field in _IMAGE_FIELDS:
            new_image[field] = image.pop(field, None)

        new_image['tags'] = image.pop('tags', [])
        new_image['status'] = image.pop('status').lower()
        for field in ('min_ram', 'min_disk', 'size', 'virtual_size'):
            new_image[field] = _pop_int(new_image, field)
        new_image['is_protected'] = protected
        new_image['locations'] = image.pop('locations', [])

        metadata = image.pop('metadata', {}) or {}
        for key, val in metadata.items():
            properties.setdefault(key, val)

        for key, val in image.items():
            properties.setdefault(key, val)
        new_image['properties'] = properties
        new_image['is_public'] = is_public
        new_image['visibility'] = visibility

        # Backwards compat with glance
        if not self.strict_mode:
            for key, val in properties.items():
                if key != 'properties':
                    new_image[key] = val
            new_image['protected'] = protected
            new_image['metadata'] = properties
            new_image['created'] = new_image['created_at']
            new_image['updated'] = new_image['updated_at']
            new_image['minDisk'] = new_image['min_disk']
            new_image['minRam'] = new_image['min_ram']
        return new_image

    # TODO(stephenfin): Remove this once we get rid of support for nova
    # secgroups
    def _normalize_secgroups(self, groups):
        """Normalize the structure of security groups

        This makes security group dicts, as returned from nova, look like the
        security group dicts as returned from neutron. This does not make them
        look exactly the same, but it's pretty close.

        :param list groups: A list of security group dicts.

        :returns: A list of normalized dicts.
        """
        ret = []
        for group in groups:
            ret.append(self._normalize_secgroup(group))
        return ret

    # TODO(stephenfin): Remove this once we get rid of support for nova
    # secgroups
    def _normalize_secgroup(self, group):

        ret = munch.Munch()
        # Copy incoming group because of shared dicts in unittests
        group = group.copy()

        # Discard noise
        self._remove_novaclient_artifacts(group)

        rules = self._normalize_secgroup_rules(
            group.pop('security_group_rules', group.pop('rules', [])))
        project_id = group.pop('tenant_id', '')
        project_id = group.pop('project_id', project_id)

        ret['location'] = self._get_current_location(project_id=project_id)
        ret['id'] = group.pop('id')
        ret['name'] = group.pop('name')
        ret['security_group_rules'] = rules
        ret['description'] = group.pop('description')
        ret['properties'] = group

        if self._use_neutron_secgroups():
            ret['stateful'] = group.pop('stateful', True)

        # Backwards compat with Neutron
        if not self.strict_mode:
            ret['tenant_id'] = project_id
            ret['project_id'] = project_id
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)

        return ret

    # TODO(stephenfin): Remove this once we get rid of support for nova
    # secgroups
    def _normalize_secgroup_rules(self, rules):
        """Normalize the structure of nova security group rules

        Note that nova uses -1 for non-specific port values, but neutron
        represents these with None.

        :param list rules: A list of security group rule dicts.

        :returns: A list of normalized dicts.
        """
        ret = []
        for rule in rules:
            ret.append(self._normalize_secgroup_rule(rule))
        return ret

    # TODO(stephenfin): Remove this once we get rid of support for nova
    # secgroups
    def _normalize_secgroup_rule(self, rule):
        ret = munch.Munch()
        # Copy incoming rule because of shared dicts in unittests
        rule = rule.copy()

        ret['id'] = rule.pop('id')
        ret['direction'] = rule.pop('direction', 'ingress')
        ret['ethertype'] = rule.pop('ethertype', 'IPv4')
        port_range_min = rule.get(
            'port_range_min', rule.pop('from_port', None))
        if port_range_min == -1:
            port_range_min = None
        if port_range_min is not None:
            port_range_min = int(port_range_min)
        ret['port_range_min'] = port_range_min
        port_range_max = rule.pop(
            'port_range_max', rule.pop('to_port', None))
        if port_range_max == -1:
            port_range_max = None
        if port_range_min is not None:
            port_range_min = int(port_range_min)
        ret['port_range_max'] = port_range_max
        ret['protocol'] = rule.pop('protocol', rule.pop('ip_protocol', None))
        ret['remote_ip_prefix'] = rule.pop(
            'remote_ip_prefix', rule.pop('ip_range', {}).get('cidr', None))
        ret['security_group_id'] = rule.pop(
            'security_group_id', rule.pop('parent_group_id', None))
        ret['remote_group_id'] = rule.pop('remote_group_id', None)
        project_id = rule.pop('tenant_id', '')
        project_id = rule.pop('project_id', project_id)
        ret['location'] = self._get_current_location(project_id=project_id)
        ret['properties'] = rule

        # Backwards compat with Neutron
        if not self.strict_mode:
            ret['tenant_id'] = project_id
            ret['project_id'] = project_id
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)
        return ret

    def _normalize_server(self, server):
        ret = munch.Munch()
        # Copy incoming server because of shared dicts in unittests
        # Wrap the copy in munch so that sub-dicts are properly munched
        server = munch.Munch(server)

        self._remove_novaclient_artifacts(server)

        ret['id'] = server.pop('id')
        ret['name'] = server.pop('name')

        server['flavor'].pop('links', None)
        ret['flavor'] = server.pop('flavor')
        # From original_names from sdk
        server.pop('flavorRef', None)

        # OpenStack can return image as a string when you've booted
        # from volume
        image = server.pop('image', None)
        if str(image) != image:
            image = munch.Munch(id=image['id'])

        ret['image'] = image
        # From original_names from sdk
        server.pop('imageRef', None)
        # From original_names from sdk
        ret['block_device_mapping'] = server.pop('block_device_mapping_v2', {})

        project_id = server.pop('tenant_id', '')
        project_id = server.pop('project_id', project_id)

        az = _pop_or_get(
            server, 'OS-EXT-AZ:availability_zone', None, self.strict_mode)
        # the server resource has this already, but it's missing az info
        # from the resource.
        # TODO(mordred) create_server is still normalizing servers that aren't
        # from the resource layer.
        ret['location'] = server.pop(
            'location', self._get_current_location(
                project_id=project_id, zone=az))

        # Ensure volumes is always in the server dict, even if empty
        ret['volumes'] = _pop_or_get(
            server, 'os-extended-volumes:volumes_attached',
            [], self.strict_mode)

        config_drive = server.pop(
            'has_config_drive', server.pop('config_drive', False))
        ret['has_config_drive'] = _to_bool(config_drive)

        host_id = server.pop('hostId', server.pop('host_id', None))
        ret['host_id'] = host_id

        ret['progress'] = _pop_int(server, 'progress')

        # Leave these in so that the general properties handling works
        ret['disk_config'] = _pop_or_get(
            server, 'OS-DCF:diskConfig', None, self.strict_mode)
        for key in (
                'OS-EXT-STS:power_state',
                'OS-EXT-STS:task_state',
                'OS-EXT-STS:vm_state',
                'OS-SRV-USG:launched_at',
                'OS-SRV-USG:terminated_at',
                'OS-EXT-SRV-ATTR:hypervisor_hostname',
                'OS-EXT-SRV-ATTR:instance_name',
                'OS-EXT-SRV-ATTR:user_data',
                'OS-EXT-SRV-ATTR:host',
                'OS-EXT-SRV-ATTR:hostname',
                'OS-EXT-SRV-ATTR:kernel_id',
                'OS-EXT-SRV-ATTR:launch_index',
                'OS-EXT-SRV-ATTR:ramdisk_id',
                'OS-EXT-SRV-ATTR:reservation_id',
                'OS-EXT-SRV-ATTR:root_device_name',
                'OS-SCH-HNT:scheduler_hints',
        ):
            short_key = key.split(':')[1]
            ret[short_key] = _pop_or_get(server, key, None, self.strict_mode)

        # Protect against security_groups being None
        ret['security_groups'] = server.pop('security_groups', None) or []

        # NOTE(mnaser): The Nova API returns the creation date in `created`
        #               however the Shade contract returns `created_at` for
        #               all resources.
        ret['created_at'] = server.get('created')

        for field in _SERVER_FIELDS:
            ret[field] = server.pop(field, None)
        if not ret['networks']:
            ret['networks'] = {}

        ret['interface_ip'] = ''

        ret['properties'] = server.copy()

        # Backwards compat
        if not self.strict_mode:
            ret['hostId'] = host_id
            ret['config_drive'] = config_drive
            ret['project_id'] = project_id
            ret['tenant_id'] = project_id
            # TODO(efried): This is hardcoded to 'compute' because this method
            # should only ever be used by the compute proxy. (That said, it
            # doesn't appear to be used at all, so can we get rid of it?)
            ret['region'] = self.config.get_region_name('compute')
            ret['cloud'] = self.config.name
            ret['az'] = az
            for key, val in ret['properties'].items():
                ret.setdefault(key, val)
        return ret

    def _normalize_compute_usage(self, usage):
        """ Normalize a compute usage object """

        usage = usage.copy()

        # Discard noise
        self._remove_novaclient_artifacts(usage)
        project_id = usage.pop('tenant_id', None)

        ret = munch.Munch(
            location=self._get_current_location(project_id=project_id),
        )
        for key in (
                'max_personality',
                'max_personality_size',
                'max_server_group_members',
                'max_server_groups',
                'max_server_meta',
                'max_total_cores',
                'max_total_instances',
                'max_total_keypairs',
                'max_total_ram_size',
                'total_cores_used',
                'total_hours',
                'total_instances_used',
                'total_local_gb_usage',
                'total_memory_mb_usage',
                'total_ram_used',
                'total_server_groups_used',
                'total_vcpus_usage'):
            ret[key] = usage.pop(key, 0)
        ret['started_at'] = usage.pop('start', None)
        ret['stopped_at'] = usage.pop('stop', None)
        ret['server_usages'] = self._normalize_server_usages(
            usage.pop('server_usages', []))
        ret['properties'] = usage
        return ret

    def _normalize_server_usage(self, server_usage):
        """ Normalize a server usage object """

        server_usage = server_usage.copy()
        # TODO(mordred) Right now there is already a location on the usage
        # object. Including one here seems verbose.
        server_usage.pop('tenant_id')
        ret = munch.Munch()

        ret['ended_at'] = server_usage.pop('ended_at', None)
        ret['started_at'] = server_usage.pop('started_at', None)
        for key in (
                'flavor',
                'instance_id',
                'name',
                'state'):
            ret[key] = server_usage.pop(key, '')
        for key in (
                'hours',
                'local_gb',
                'memory_mb',
                'uptime',
                'vcpus'):
            ret[key] = server_usage.pop(key, 0)
        ret['properties'] = server_usage
        return ret

    def _normalize_server_usages(self, server_usages):
        ret = []
        for server_usage in server_usages:
            ret.append(self._normalize_server_usage(server_usage))
        return ret

    def _normalize_coe_clusters(self, coe_clusters):
        ret = []
        for coe_cluster in coe_clusters:
            ret.append(self._normalize_coe_cluster(coe_cluster))
        return ret

    def _normalize_coe_cluster(self, coe_cluster):
        """Normalize Magnum COE cluster."""
        coe_cluster = coe_cluster.copy()

        # Discard noise
        coe_cluster.pop('links', None)

        c_id = coe_cluster.pop('uuid')

        ret = munch.Munch(
            id=c_id,
            location=self._get_current_location(),
        )

        if not self.strict_mode:
            ret['uuid'] = c_id

        for key in (
                'status',
                'cluster_template_id',
                'stack_id',
                'keypair',
                'master_count',
                'create_timeout',
                'node_count',
                'name'):
            if key in coe_cluster:
                ret[key] = coe_cluster.pop(key)

        ret['properties'] = coe_cluster
        return ret

    def _normalize_cluster_templates(self, cluster_templates):
        ret = []
        for cluster_template in cluster_templates:
            ret.append(self._normalize_cluster_template(cluster_template))
        return ret

    def _normalize_cluster_template(self, cluster_template):
        """Normalize Magnum cluster_templates."""
        cluster_template = cluster_template.copy()

        # Discard noise
        cluster_template.pop('links', None)
        cluster_template.pop('human_id', None)
        # model_name is a magnumclient-ism
        cluster_template.pop('model_name', None)

        ct_id = cluster_template.pop('uuid')

        ret = munch.Munch(
            id=ct_id,
            location=self._get_current_location(),
        )
        ret['is_public'] = cluster_template.pop('public')
        ret['is_registry_enabled'] = cluster_template.pop('registry_enabled')
        ret['is_tls_disabled'] = cluster_template.pop('tls_disabled')
        # pop floating_ip_enabled since we want to hide it in a future patch
        fip_enabled = cluster_template.pop('floating_ip_enabled', None)
        if not self.strict_mode:
            ret['uuid'] = ct_id
            if fip_enabled is not None:
                ret['floating_ip_enabled'] = fip_enabled
            ret['public'] = ret['is_public']
            ret['registry_enabled'] = ret['is_registry_enabled']
            ret['tls_disabled'] = ret['is_tls_disabled']

        # Optional keys
        for (key, default) in (
                ('fixed_network', None),
                ('fixed_subnet', None),
                ('http_proxy', None),
                ('https_proxy', None),
                ('labels', {}),
                ('master_flavor_id', None),
                ('no_proxy', None)):
            if key in cluster_template:
                ret[key] = cluster_template.pop(key, default)

        for key in (
                'apiserver_port',
                'cluster_distro',
                'coe',
                'created_at',
                'dns_nameserver',
                'docker_volume_size',
                'external_network_id',
                'flavor_id',
                'image_id',
                'insecure_registry',
                'keypair_id',
                'name',
                'network_driver',
                'server_type',
                'updated_at',
                'volume_driver'):
            ret[key] = cluster_template.pop(key)

        ret['properties'] = cluster_template
        return ret

    def _normalize_magnum_services(self, magnum_services):
        ret = []
        for magnum_service in magnum_services:
            ret.append(self._normalize_magnum_service(magnum_service))
        return ret

    def _normalize_magnum_service(self, magnum_service):
        """Normalize Magnum magnum_services."""
        magnum_service = magnum_service.copy()

        # Discard noise
        magnum_service.pop('links', None)
        magnum_service.pop('human_id', None)
        # model_name is a magnumclient-ism
        magnum_service.pop('model_name', None)

        ret = munch.Munch(location=self._get_current_location())

        for key in (
                'binary',
                'created_at',
                'disabled_reason',
                'host',
                'id',
                'report_count',
                'state',
                'updated_at'):
            ret[key] = magnum_service.pop(key)
        ret['properties'] = magnum_service
        return ret

    def _normalize_machines(self, machines):
        """Normalize Ironic Machines"""
        ret = []
        for machine in machines:
            ret.append(self._normalize_machine(machine))
        return ret

    def _normalize_machine(self, machine):
        """Normalize Ironic Machine"""
        if isinstance(machine, resource.Resource):
            machine = machine._to_munch()
        else:
            machine = machine.copy()

        # Discard noise
        self._remove_novaclient_artifacts(machine)

        return machine
