import os
import apt
from charmhelpers.core.templating import render


DEFAULT_REDIS_CONF = os.path.join('/', 'etc', 'redis', 'redis.conf')
CHARM_REDIS_CONF = os.path.join('/', 'etc', 'redis', 'redis-charm.conf')


def render_conf(cfg_path, cfg_tmpl, owner='root',
                group='root', ctxt={}, perms=0o644):
    if os.path.exists(cfg_path):
        os.remove(cfg_path)
    render(source=cfg_tmpl, target=cfg_path, owner=owner,
           group=group, perms=perms, context=ctxt)


def get_redis_version(pkg):
    """Return redis-server version
    """
    cache = apt.cache.Cache()
    for pkgname in cache.keys():
        if pkgname == pkg:
            target_pkg = cache[pkg]
            pkg_installed = target_pkg.installed
            if pkg_installed:
                return pkg_installed.version.split(":")[1]
    return False
