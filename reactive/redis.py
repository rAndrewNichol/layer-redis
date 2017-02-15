import os
from subprocess import call
from charms.reactive import when, when_not, set_state
from charmhelpers.core.hookenv import (
    application_version_set,
    unit_private_ip,
    status_set,
    config,
    open_port
)

from charmhelpers.core.host import (
    service_restart,
    service_running,
    service_start,
)

from charms.layer.redis import(
    render_conf,
    get_redis_version,
    DEFAULT_REDIS_CONF,
    CHARM_REDIS_CONF
)


@when_not('redis.auto.start.configured')
def configure_autostart():
    call("systemctl enable redis-server.service".split())
    set_state('redis.auto.start.configured')


@when_not('redis.ready')
def config_redis():
    ctxt={'host': unit_private_ip(),
          'port': config('port'),
          'databases': config('databases'),
          'log_level': config('log-level'),
          'tcp_keepalive': config('tcp-keepalive'),
          'timeout': config('timeout')}

    if config('password'):
        ctxt['password'] = config('password')

    render_conf(CHARM_REDIS_CONF, 'redis.conf.tmpl', ctxt=ctxt)

    with open(DEFAULT_REDIS_CONF, 'a') as conf_file:
        conf_file.write('include {}\n'.format(CHARM_REDIS_CONF))

    if service_running('redis-server'):
        service_restart('redis-server')
    else:
        service_start('redis-server')

    open_port(config('port'))
    status_set('active', 'Redis available')
    set_state('redis.ready')


@when('redis.ready')
@when_not('redis.version.set')
def set_redis_version():
    """Set redis version
    """
    version = get_redis_version('redis-server')
    if version:
        application_version_set(version)
        set_state('redis.version.set')
    else:
        status_set('blocked', "Cannot get redis-server version")

@when('redis.connected', 'redis.ready', 'redis.version.set')
@when_not('redis.data.set', 'redis.configured')
def set_relational_data(redis):
    if config('password'):
        redis.configure(port=config('port'), password=config('password'))
    else:
        redis.configure(port=config('port'))
    set_state('redis.data.set')
