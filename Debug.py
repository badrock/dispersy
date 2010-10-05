import socket

from Crypto import rsa_generate_key, rsa_to_public_pem, rsa_to_private_pem
from Privilege import PublicPrivilege, LinearPrivilege
from Message import Message
from Destination import CommunityDestination
from Distribution import DirectDistribution, LastSyncDistribution, FullSyncDistribution
from Permission import PermitPermission
from Member import MyMember
from Print import dprint
from Bloomfilter import BloomFilter

class Node(object):
    _socket_range = (8000, 8999)
    _socket_pool = {}
    _socket_counter = 0

    def __init__(self):
        self._socket = None
        self._my_member = None
        self._community = None
        self._dispersy_sync_privilege = PublicPrivilege(u"dispersy-sync", DirectDistribution(), CommunityDestination()).implement("DISABLED FOR DEBUG", sync=False)

    @property
    def socket(self):
        return self._socket

    def init_socket(self):
        assert self._socket is None
        port = Node._socket_range[0] + Node._socket_counter % (Node._socket_range[1] - Node._socket_range[0])
        Node._socket_counter += 1

        if not port in Node._socket_pool:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("localhost", port))
            s.setblocking(True)
            Node._socket_pool[port] = s
            if __debug__: dprint("create socket ", port)

        elif __debug__:
            dprint("reuse socket ", port, level="warning")

        self._socket = Node._socket_pool[port]

    @property
    def my_member(self):
        return self._my_member

    def init_my_member(self, bits=512):
        rsa = rsa_generate_key(bits)
        self._my_member = MyMember.get_instance(rsa_to_public_pem(rsa), rsa_to_private_pem(rsa))

    @property
    def community(self):
        return self._community

    def set_community(self, community):
        self._community = community

    def create_message(self, distribution, destination, permission):
        return Message(self._community, self._my_member, distribution, destination, permission)

    def encode_message(self, message):
        return self._community.get_conversion().encode_message(message)

    def send_packet(self, packet, address):
        dprint(len(packet), " bytes to ", address[0], ":", address[1])
        return self._socket.sendto(packet, address)

    def send_message(self, message, address):
        dprint(message.permission.privilege.name, "^", message.permission.name, " to ", address[0], ":", address[1])
        return self.send_packet(self.encode_message(message), address)

    def receive_packet(self, timeout=10.0, addresses=None, packets=None):
        assert isinstance(timeout, float)
        assert isinstance(addresses, (type(None), list))
        assert isinstance(packets, (type(None), list))
        self._socket.settimeout(timeout)
        while True:
            try:
                packet, address = self._socket.recvfrom(10240)
            except:
                raise

            if not (addresses is None or address in addresses or (address[0] == "127.0.0.1" and ("0.0.0.0", address[1]) in addresses)):
                continue

            if not (packets is None or packet in packets):
                continue

            dprint(len(packet), " bytes from ", address[0], ":", address[1])
            return address, packet
        
    def receive_message(self, timeout=10.0, addresses=None, packets=None, distributions=None, destinations=None, permissions=None, privileges=None, successful_decode=True):
        assert isinstance(timeout, float)
        assert isinstance(addresses, (type(None), list))
        assert isinstance(packets, (type(None), list))
        assert isinstance(distributions, (type(None), list))
        assert isinstance(destinations, (type(None), list))
        assert isinstance(permissions, (type(None), list))
        assert isinstance(privileges, (type(None), list))
        assert isinstance(successful_decode, bool)
        self._socket.settimeout(timeout)
        while True:
            address, packet = self.receive_packet(timeout, addresses, packets)

            try:
                message = self._community.get_conversion().decode_message(packet)
            except:
                if successful_decode:
                    continue
                raise

            if not (distributions is None or isinstance(message.distribution, distributions)):
                continue

            if not (destinations is None or isinstance(message.destination, destinations)):
                continue

            if not (permissions is None or isinstance(message.permission, permissions)):
                continue

            if not (privileges is None or message.permission.privilege in privileges):
                continue
            
            dprint(message.permission.privilege.name, "^", message.permission.name, " (", len(packet), " bytes) from ", address[0], ":", address[1])
            return address, packet, message
            
    def create_dispersy_sync_message(self, bloom_global_time, bloom_packets, global_time):
        assert isinstance(bloom_global_time, (int, long))
        assert isinstance(bloom_packets, list)
        assert not filter(lambda x: not isinstance(x, str), bloom_packets)
        assert isinstance(global_time, (int, long))
        bloom_filter = BloomFilter(1000, 0.001)
        map(bloom_filter.add, bloom_packets)
        distribution = self._dispersy_sync_privilege.distribution.implement(global_time)
        destination = self._dispersy_sync_privilege.destination.implement()
        permission = PermitPermission(self._dispersy_sync_privilege, (bloom_global_time, bloom_filter))
        return self.create_message(distribution, destination, permission)

class DiscoveryNode(Node):
    def __init__(self, *args, **kargs):
        super(DiscoveryNode, self).__init__(*args, **kargs)
        self._community_metadata_privilege = PublicPrivilege(u"community-metadata", FullSyncDistribution(), CommunityDestination()).implement("DISABLED FOR DEBUG", sync=False)
        self._user_metadata_privilege = PublicPrivilege(u"user-metadata", LastSyncDistribution(), CommunityDestination()).implement("DISABLED FOR DEBUG", sync=False)

    def create_community_metadata_message(self, cid, alias, comment, global_time, sequence_number):
        distribution = self._community_metadata_privilege.distribution.implement(global_time, sequence_number)
        destination = self._community_metadata_privilege.destination.implement()
        permission = PermitPermission(self._community_metadata_privilege, (cid, alias, comment))
        return self.create_message(distribution, destination, permission)

    def create_user_metadata_message(self, address, alias, comment, global_time):
        distribution = self._user_metadata_privilege.distribution.implement(global_time)
        destination = self._user_metadata_privilege.destination.implement()
        permission = PermitPermission(self._user_metadata_privilege, (address, alias, comment))
        return self.create_message(distribution, destination, permission)
    
class ForumNode(DiscoveryNode):
    def __init__(self, *args, **kargs):
        super(ForumNode, self).__init__(*args, **kargs)
        self._set_settings_privilege = LinearPrivilege(u"set-settings", LastSyncDistribution(100, 100, 0.001), CommunityDestination()).implement("DISABLED FOR DEBUG", sync=False)
        self._create_thread_privilege = LinearPrivilege(u"create-thread", FullSyncDistribution(100, 100, 0.001), CommunityDestination()).implement("DISABLED FOR DEBUG", sync=False)
        self._create_post_privilege = LinearPrivilege(u"create-post", FullSyncDistribution(100, 100, 0.001), CommunityDestination()).implement("DISABLED FOR DEBUG", sync=False)

    def create_set_settings_message(self, title, description, global_time):
        distribution = self._set_settings_privilege.distribution.implement(global_time)
        destination = self._set_settings_privilege.destination.implement()
        permission = PermitPermission(self._set_settings_privilege, (title, description))
        return self.create_message(distribution, destination, permission)

    def create_create_thread_message(self, key, title, comment, global_time, sequence_number):
        distribution = self._create_thread_privilege.distribution.implement(global_time, sequence_number)
        destination = self._create_thread_privilege.destination.implement()
        permission = PermitPermission(self._create_thread_privilege, (key, title, comment))
        return self.create_message(distribution, destination, permission)

    def create_create_post_message(self, key, comment, global_time, sequence_number):
        distribution = self._create_post_privilege.distribution.implement(global_time, sequence_number)
        destination = self._create_post_privilege.destination.implement()
        permission = PermitPermission(self._create_post_privilege, (key, comment))
        return self.create_message(distribution, destination, permission)
        
