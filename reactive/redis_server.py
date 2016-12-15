from charms.reactive import when, when_not, set_state
from charmhelpers.core.hookenv import unit_private_ip, status_set, config, open_port


@when_not('redis.configured')
def config_redis():
    open_port(config('port'))
    set_state('redis.port.configured')

@when('redis.available', 'redis.port.configured')
@when_not('redis.data.set')
def set_relational_data(redis):
    redis.provide_data(port=config('port'), password=config('password'))
    set_state('redis.data.set')
