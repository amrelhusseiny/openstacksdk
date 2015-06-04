# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import mock

import shade
from shade import meta
from shade.tests.unit import base
from shade.tests import fakes


neutron_grp_obj = fakes.FakeSecgroup(
    id='1',
    name='neutron-sec-group',
    description='Test Neutron security group',
    rules=[
        dict(id='1', port_range_min=80, port_range_max=81,
             protocol='tcp', remote_ip_prefix='0.0.0.0/0')
    ]
)


nova_grp_obj = fakes.FakeSecgroup(
    id='2',
    name='nova-sec-group',
    description='Test Nova security group #1',
    rules=[
        dict(id='2', from_port=8000, to_port=8001, ip_protocol='tcp',
             ip_range=dict(cidr='0.0.0.0/0'), parent_group_id=None)
    ]
)


# Neutron returns dicts instead of objects, so the dict versions should
# be used as expected return values from neutron API methods.
neutron_grp_dict = meta.obj_to_dict(neutron_grp_obj)
nova_grp_dict = meta.obj_to_dict(nova_grp_obj)


class TestSecurityGroups(base.TestCase):

    def setUp(self):
        super(TestSecurityGroups, self).setUp()
        self.cloud = shade.openstack_cloud()

    @mock.patch.object(shade.OpenStackCloud, 'neutron_client')
    @mock.patch.object(shade.OpenStackCloud, 'nova_client')
    def test_list_security_groups_neutron(self, mock_nova, mock_neutron):
        self.cloud.secgroup_source = 'neutron'
        self.cloud.list_security_groups()
        self.assertTrue(mock_neutron.list_security_groups.called)
        self.assertFalse(mock_nova.security_groups.list.called)

    @mock.patch.object(shade.OpenStackCloud, 'neutron_client')
    @mock.patch.object(shade.OpenStackCloud, 'nova_client')
    def test_list_security_groups_nova(self, mock_nova, mock_neutron):
        self.cloud.secgroup_source = 'nova'
        self.cloud.list_security_groups()
        self.assertFalse(mock_neutron.list_security_groups.called)
        self.assertTrue(mock_nova.security_groups.list.called)

    @mock.patch.object(shade.OpenStackCloud, 'neutron_client')
    @mock.patch.object(shade.OpenStackCloud, 'nova_client')
    def test_list_security_groups_none(self, mock_nova, mock_neutron):
        self.cloud.secgroup_source = None
        self.assertRaises(shade.OpenStackCloudUnavailableFeature,
                          self.cloud.list_security_groups)
        self.assertFalse(mock_neutron.list_security_groups.called)
        self.assertFalse(mock_nova.security_groups.list.called)

    @mock.patch.object(shade.OpenStackCloud, 'neutron_client')
    def test_delete_security_group_neutron(self, mock_neutron):
        self.cloud.secgroup_source = 'neutron'
        neutron_return = dict(security_groups=[neutron_grp_dict])
        mock_neutron.list_security_groups.return_value = neutron_return
        self.cloud.delete_security_group('1')
        mock_neutron.delete_security_group.assert_called_once_with(
            security_group='1'
        )

    @mock.patch.object(shade.OpenStackCloud, 'nova_client')
    def test_delete_security_group_nova(self, mock_nova):
        self.cloud.secgroup_source = 'nova'
        nova_return = [nova_grp_obj]
        mock_nova.security_groups.list.return_value = nova_return
        self.cloud.delete_security_group('2')
        mock_nova.security_groups.delete.assert_called_once_with(
            group='2'
        )

    @mock.patch.object(shade.OpenStackCloud, 'neutron_client')
    def test_delete_security_group_neutron_not_found(self, mock_neutron):
        self.cloud.secgroup_source = 'neutron'
        neutron_return = dict(security_groups=[neutron_grp_dict])
        mock_neutron.list_security_groups.return_value = neutron_return
        self.cloud.delete_security_group('doesNotExist')
        self.assertFalse(mock_neutron.delete_security_group.called)

    @mock.patch.object(shade.OpenStackCloud, 'nova_client')
    def test_delete_security_group_nova_not_found(self, mock_nova):
        self.cloud.secgroup_source = 'nova'
        nova_return = [nova_grp_obj]
        mock_nova.security_groups.list.return_value = nova_return
        self.cloud.delete_security_group('doesNotExist')
        self.assertFalse(mock_nova.security_groups.delete.called)

    @mock.patch.object(shade.OpenStackCloud, 'neutron_client')
    @mock.patch.object(shade.OpenStackCloud, 'nova_client')
    def test_delete_security_group_none(self, mock_nova, mock_neutron):
        self.cloud.secgroup_source = None
        self.assertRaises(shade.OpenStackCloudUnavailableFeature,
                          self.cloud.delete_security_group,
                          'doesNotExist')
        self.assertFalse(mock_neutron.delete_security_group.called)
        self.assertFalse(mock_nova.security_groups.delete.called)
