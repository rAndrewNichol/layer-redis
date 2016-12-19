import os
from charms.reactive import when, when_not, set_state
from charmhelpers.core.hookenv import (
    unit_private_ip,
    status_set,
    config,
    open_port
)
from charmhelpers.core.templating import render

from charmhelpers.core.host import (
    service_restart,
    service_running,
    service_start,
)


DEFAULT_REDIS_CONF = os.path.join('/', 'etc', 'redis', 'redis.conf')
CHARM_REDIS_CONF = os.path.join('/', 'etc', 'redis', 'redis-charm.conf')


def render_conf(cfg_path, cfg_tmpl, owner='root',
                group='root', ctxt={}, perms=0o644):
    if os.path.exists(cfg_path):
        os.remove(cfg_path)
    render(source=cfg_tmpl, target=cfg_path, owner=owner,
           group=group, perms=perms, context=ctxt)


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


@when('redis.connected', 'redis.ready')
@when_not('redis.data.set', 'redis.configured')
def set_relational_data(redis):
    if config('password'):
        redis.configure(port=config('port'), password=config('password'))
    else:
        redis.configure(port=config('port'))
    set_state('redis.data.set')
