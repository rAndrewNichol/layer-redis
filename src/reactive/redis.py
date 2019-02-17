from subprocess import (
    call,
    check_output,
    Popen,
    PIPE,
    STDOUT,
)

from charms.reactive import (
    clear_flag,
    endpoint_from_flag,
    hook,
    is_flag_set,
    set_flag,
    when,
    when_any,
    when_not,
)

from charmhelpers.core.hookenv import (
    application_version_set,
    local_unit,
    log,
    config,
    open_port,
    unit_private_ip,
)

from charmhelpers.core.host import (
    is_container,
    service_restart,
    service_running,
    service_start,
)

import charms.leadership

from charms.layer import status

from charms.layer.redis import (
    render_conf,
    get_redis_version,
    REDIS_CLI,
    REDIS_DIR,
    REDIS_CONF,
    REDIS_CLUSTER_CONF,
    REDIS_SERVICE,
)


@when_not('redis.cluster.standalone.determined')
def set_flag_for_redis_cluster_if_enabled():
    if config('cluster-enabled'):
        set_flag('redis.cluster.enabled')
    set_flag('redis.cluster.standalone.determined')


@when('redis.cluster.enabled')
@when_not('leadership.set.cluster_created')
@when_any('endpoint.cluster.peer.joined',
          'endpoint.cluster.peer.changed')
def ensure_sufficient_masters():
    """Redis enforces us to use at minimum 3 master nodes.
    Set leader flag indicating we have met the minimum # nodes.
    """

    if is_flag_set('endpoint.cluster.peer.joined'):
        endpoint = 'endpoint.cluster.peer.joined'
    elif is_flag_set('endpoint.cluster.peer.changed'):
        endpoint = 'endpoint.cluster.peer.changed'
    else:
        status.blocked('No peer endpoint set')
        return

    peers = endpoint_from_flag(endpoint).all_units
    peer_ips = ["{}:6379".format(peer._data['private-address'])
                for peer in peers if peer._data is not None]

    if len(peer_ips) > 1:
        status.active(
            "Minimum # masters available, got {}.".format(len(peer_ips)+1))
        init_masters = \
            " ".join(peer_ips) + " {}:6379".format(unit_private_ip())
        charms.leadership.leader_set(init_masters=init_masters)

    clear_flag('endpoint.cluster.peer.joined')
    clear_flag('endpoint.cluster.peer.changed')


@when_not('redis.system.configured')
def configure_system_for_redis():
    if not is_container():
        with open('/etc/sysctl.conf', 'a') as f:
            f.write("\nvm.overcommit_memory = 1")
        call('sysctl vm.overcommit_memory=1'.split())

        with open('/sys/kernel/mm/transparent_hugepage/enabled', 'w') as f:
            f.write('never')

        with open('/proc/sys/net/core/somaxconn', 'w') as f:
            f.write('1024')

    set_flag('redis.system.configured')


@when('snap.installed.redis-bdx',
      'redis.system.configured',
      'redis.cluster.standalone.determined')
@when_not('redis.system.pre-init.complete')
def set_pre_init():
    set_flag('redis.system.pre-init.complete')


@when('redis.system.pre-init.complete')
@when_not('redis.ready')
def write_config_start_restart_redis():
    ctxt = {'port': config('port'),
            'databases': config('databases'),
            'log_level': config('log-level'),
            'tcp_keepalive': config('tcp-keepalive'),
            'timeout': config('timeout'),
            'redis_dir': REDIS_DIR}

    if config('cluster-enabled'):
        ctxt['cluster_conf'] = REDIS_CLUSTER_CONF
    if config('password'):
        ctxt['password'] = config('password')

    render_conf(REDIS_CONF, 'redis.conf.tmpl', ctxt=ctxt)

    if service_running(REDIS_SERVICE):
        service_restart(REDIS_SERVICE)
    else:
        service_start(REDIS_SERVICE)

    status.active("Redis {} available".format(
        "cluster" if config('cluster-enabled') else "singleton"))
    set_flag('redis.ready')


@when('redis.ready')
@when_not('redis.port.accessible')
def open_redis_port():
    """Open redis port
    """
    open_port(config('port'))
    set_flag('redis.port.accessible')


@when('redis.ready')
@when_not('redis.version.set')
def set_redis_version():
    """Set redis version
    """
    version = get_redis_version()
    if version:
        application_version_set(version)
        set_flag('redis.version.set')
    else:
        status.blocked("Cannot get redis-server version")
        return


@when('redis.ready',
      'redis.cluster.enabled')
@when_not('leadership.set.init_masters')
def waiting_for_min_masters():
    status.blocked("Need at least 3 master nodes to bootstrap cluster...")
    return


@when('leadership.set.cluster_node_ips')
def are_we_in_status():
    """Determine if this node is part of the cluster.
    """

    cluster_node_ips = \
        charms.leadership.leader_get("cluster_node_ips").split(",")

    if unit_private_ip() in cluster_node_ips:
        status.active("cluster successfully joined")
        set_flag('redis.cluster.joined')


@when('redis.ready',
      'leadership.is_leader',
      'redis.cluster.enabled',
      'redis.port.accessible',
      'leadership.set.init_masters')
@when_not('redis.cluster.created',
          'leadership.set.cluster_created')
def create_redis_cluster():
    """Create redis cluster
    """

    status.maintenance("creating cluster...")

    init_masters = charms.leadership.leader_get("init_masters")

    cmd = ('{} --cluster create {} --cluster-replicas 0').format(
            REDIS_CLI, init_masters)
    p = Popen(cmd.split(), stdout=PIPE, stdin=PIPE, stderr=STDOUT)
    std_out = p.communicate(input='yes\n'.encode())[0]

    log(std_out)

    charms.leadership.leader_set(cluster_created="true")

    set_flag('redis.cluster.joined')
    set_flag('redis.cluster.created')


@when('redis.cluster.joined')
def cluster_joined_status():
    status.active("successfully clustered")


@when('redis.ready',
      'redis.cluster.enabled',
      'redis.cluster.created',
      'leadership.set.cluster_created',
      'leadership.is_leader')
@when_any('endpoint.cluster.peer.joined',
          'endpoint.cluster.peer.changed')
def add_new_peer_nodes_to_cluster():
    """Add new peers to cluster
    """

    if is_flag_set('endpoint.cluster.peer.joined'):
        endpoint = 'endpoint.cluster.peer.joined'
    elif is_flag_set('endpoint.cluster.peer.changed'):
        endpoint = 'endpoint.cluster.peer.changed'
    else:
        status.blocked('No peer endpoint set')
        return

    # Get the known cluster peer ip addressese from juju perspective
    peers = endpoint_from_flag(endpoint).all_units
    peer_ips = [peer._data['private-address']
                for peer in peers if peer._data is not None]

    # Get the known cluster node ips from redis point of view
    cluster_node_ips = []
    cmd = '{} -n 0 cluster nodes'.format(REDIS_CLI)
    out = check_output(cmd, shell=True)
    log(out)
    for node in out.decode().split('\n')[:-1]:
        node = node.split()
        cluster_node_ips.append(node[1].split("@")[0].split(":")[0])

    # Compare the nodes in the cluster to the peer nodes that juju is aware of
    # Register nodes that are juju peers, but not part of the cluster
    node_added = False
    for ip in peer_ips:
        if ip not in cluster_node_ips:
            node_added = True
            cmd = "{} --cluster add-node {}:6379 {}:6379".format(
                 REDIS_CLI, ip, unit_private_ip())
            out = check_output(cmd, shell=True)
            log(out)

    # Give the cluster a second to recognize the new node
    from time import sleep
    sleep(1)

    if node_added:
        # Get the known cluster node ids (including the recently added node)
        cluster_node_ids = []
        cluster_node_ips = []
        cmd = '{} -n 0 cluster nodes'.format(REDIS_CLI)
        out = check_output(cmd, shell=True)
        log(out)
        for node in out.decode().split('\n')[:-1]:
            node = node.split()
            cluster_node_ids.append(node[0])
            cluster_node_ips.append(node[1].split("@")[0].split(":")[0])
  
        charms.leadership.leader_set(cluster_node_ips=",".join(cluster_node_ips))
        # Generate the weights string for the rebalance command
        node_weights = " ".join(["{}=1".format(node_id)
                                 for node_id in cluster_node_ids])
        cmd = ("{} --cluster rebalance --cluster-weight {} "
               "--cluster-timeout 3600 --cluster-use-empty-masters "
               "{}:6379").format(REDIS_CLI, node_weights, unit_private_ip())
        out = check_output(cmd, shell=True)
        log(out)

    clear_flag('endpoint.cluster.peer.joined')
    clear_flag('endpoint.cluster.peer.changed')


# Client Relation
@when('endpoint.redis.joined')
def provide_client_relation_data():
    endpoint = endpoint_from_flag('endpoint.redis.joined')
    ctxt = {'host': unit_private_ip(), 'port': config('port')}
    if config('password'):
        ctxt['password'] = config('password')
    endpoint.configure(**ctxt)


# Set up Nagios checks when the nrpe-external-master subordinate is related
@when('nrpe-external-master.available')
@when_not('redis.nagios-setup.complete')
def setup_nagios(nagios):
    conf = config()
    unit_name = local_unit()
    check_base = '/usr/lib/nagios/plugins/'
    process_check = check_base + 'check_procs'

    web_check = [process_check, '-c', '1:1', '-a', 'bin/redis-server']
    nagios.add_check(web_check, name="redis-serverprocess",
                     description="Check for redis-server process",
                     context=conf['nagios_context'],
                     servicegroups=conf['nagios_servicegroups'],
                     unit=unit_name)

    set_flag('redis.nagios-setup.complete')


# This is triggered on any config-changed, and after an upgrade-charm - you
# don't get the latter with @when('config.changed')
@hook('config-changed')
def set_nrpe_flag():
    clear_flag('redis.nagios-setup.complete')
