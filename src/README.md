# Redis Charm Overview

This charm provides Redis Server. Redis is an open source (BSD licensed), in-memory data structure store, used as a database, cache and message broker. It supports data structures such as strings, hashes, lists, sets, sorted sets with range queries, bitmaps, hyperloglogs and geospatial indexes with radius queries. Redis has built-in replication, Lua scripting, LRU eviction, transactions and different levels of on-disk persistence, and provides high availability via Redis Sentinel and automatic partitioning with Redis Cluster.

### Usage

```bash
juju deploy cs:~omnivector/redis
```

### metrics

It is possible to collect metrics for this charm by using `juju metrics redis`. You will receive the following output: 

```bash
UNIT   	           TIMESTAMP	           METRIC	 VALUE
redis/3	2017-09-27T21:15:09Z	  blocked_clients	     0
redis/3	2017-09-27T21:15:09Z	connected_clients	     1
redis/3	2017-09-27T21:15:09Z	       juju-units	     1
redis/3	2017-09-27T21:15:09Z	      used_memory	508800

```

### Scale out Usage

This charm supports redis-cluster. You can enable redis-cluster by setting the `cluster-enabled` config to `true`.
```
juju deploy cs:~omnivector/redis --config cluster-enabled=true
```


#### Copyright
* Omnivector Solutions (c) 2019 <info@omnivector.solutions>

#### License
* AGPLv3 (see `LICENSE` file)


### Redis Info

  - https://redis.io/
  - https://github.com/antirez/redis/issues
  - https://groups.google.com/forum/?fromgroups#!forum/redis-db
