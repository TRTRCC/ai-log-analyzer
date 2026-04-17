-- ClickHouse Database Initialization
-- Creates log storage tables

-- Create database
CREATE DATABASE IF NOT EXISTS ailoganalyzer_logs;

-- Log main table
CREATE TABLE IF NOT EXISTS ailoganalyzer_logs.logs (
    timestamp DateTime64(3),
    log_type LowCardinality(String),
    source_host String,
    source_ip String,
    facility String,
    severity LowCardinality(String),
    program String,
    pid String,
    message String,
    raw_message String,
    parsed_fields Map(String, String),
    file_id String,
    log_hash String,
    ingestion_time DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (log_type, source_host, timestamp)
SETTINGS index_granularity = 8192;

-- Create indexes for common queries
ALTER TABLE ailoganalyzer_logs.logs ADD INDEX idx_severity severity TYPE set(0) GRANULARITY 1;
ALTER TABLE ailoganalyzer_logs.logs ADD INDEX idx_source_host source_host TYPE bloom_filter GRANULARITY 1;

-- Log file fingerprints table (for deduplication)
CREATE TABLE IF NOT EXISTS ailoganalyzer_logs.log_fingerprints (
    file_hash String,
    file_name String,
    file_size UInt64,
    processed_time DateTime,
    log_count UInt64,
    processing_duration_ms UInt64
) ENGINE = ReplacingMergeTree()
ORDER BY file_hash;

-- Log statistics daily aggregation
CREATE TABLE IF NOT EXISTS ailoganalyzer_logs.log_stats_daily (
    date Date,
    log_type LowCardinality(String),
    source_host String,
    total_count UInt64,
    error_count UInt64,
    warning_count UInt64,
    info_count UInt64,
    unique_messages UInt64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, log_type, source_host);

-- Network device specific log table
CREATE TABLE IF NOT EXISTS ailoganalyzer_logs.network_logs (
    timestamp DateTime64(3),
    device_name String,
    device_type LowCardinality(String),
    device_ip String,
    log_level LowCardinality(String),
    event_type String,
    message String,
    raw_message String,
    parsed_fields Map(String, String),
    file_id String,
    ingestion_time DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (device_name, timestamp);

-- Server log table
CREATE TABLE IF NOT EXISTS ailoganalyzer_logs.server_logs (
    timestamp DateTime64(3),
    hostname String,
    host_ip String,
    log_source LowCardinality(String),
    facility String,
    severity LowCardinality(String),
    program String,
    message String,
    raw_message String,
    parsed_fields Map(String, String),
    file_id String,
    ingestion_time DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (hostname, timestamp);

-- Kubernetes log table
CREATE TABLE IF NOT EXISTS ailoganalyzer_logs.k8s_logs (
    timestamp DateTime64(3),
    namespace String,
    pod_name String,
    container_name String,
    node_name String,
    log_level LowCardinality(String),
    message String,
    raw_message String,
    parsed_fields Map(String, String),
    file_id String,
    ingestion_time DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (namespace, pod_name, timestamp);

-- Create materialized view for daily stats
CREATE MATERIALIZED VIEW IF NOT EXISTS ailoganalyzer_logs.log_stats_daily_mv
TO ailoganalyzer_logs.log_stats_daily
AS SELECT
    toDate(timestamp) as date,
    log_type,
    source_host,
    count() as total_count,
    countIf(severity = 'ERROR' OR severity = 'CRITICAL') as error_count,
    countIf(severity = 'WARNING') as warning_count,
    countIf(severity = 'INFO' OR severity = 'DEBUG') as info_count,
    uniqExact(message) as unique_messages
FROM ailoganalyzer_logs.logs
GROUP BY date, log_type, source_host;