-- AI Log Analyzer Database Initialization
-- This script creates initial tables and default data

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Departments table
CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'server_user',
    department_id UUID REFERENCES departments(id),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- AI Providers table
CREATE TABLE IF NOT EXISTS ai_providers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100),
    provider_type VARCHAR(20) NOT NULL,
    api_endpoint VARCHAR(255),
    api_key_encrypted TEXT,
    models JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,
    config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI Models table
CREATE TABLE IF NOT EXISTS ai_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id UUID REFERENCES ai_providers(id),
    model_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(100),
    max_tokens INTEGER,
    cost_per_1k_input_tokens NUMERIC(10, 6),
    cost_per_1k_output_tokens NUMERIC(10, 6),
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,
    config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Analysis Tasks table
CREATE TABLE IF NOT EXISTS analysis_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    task_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    log_type VARCHAR(20) NOT NULL DEFAULT 'all',
    time_range_start TIMESTAMP WITH TIME ZONE,
    time_range_end TIMESTAMP WITH TIME ZONE,
    devices TEXT[],
    model_id UUID REFERENCES ai_models(id),
    provider_id UUID REFERENCES ai_providers(id),
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost TEXT,
    result JSONB,
    error_message TEXT,
    progress_percent INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_tasks_status ON analysis_tasks(status);
CREATE INDEX idx_tasks_created ON analysis_tasks(created_at);

-- Reports table
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES analysis_tasks(id),
    user_id UUID REFERENCES users(id),
    report_type VARCHAR(20) NOT NULL,
    report_date DATE,
    title VARCHAR(255),
    content JSONB,
    summary TEXT,
    file_path VARCHAR(500),
    file_format VARCHAR(10) DEFAULT 'pdf',
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_reports_date ON reports(report_date);
CREATE INDEX idx_reports_created ON reports(created_at);

-- Report Subscriptions table
CREATE TABLE IF NOT EXISTS report_subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    report_type VARCHAR(20) NOT NULL,
    email VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit Logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    details TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

-- System Configs table
CREATE TABLE IF NOT EXISTS system_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value JSONB,
    description TEXT,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Scheduled Tasks table
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    cron_expression VARCHAR(100),
    interval_minutes INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP WITH TIME ZONE,
    next_run TIMESTAMP WITH TIME ZONE,
    config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Email Configs table
CREATE TABLE IF NOT EXISTS email_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    smtp_host VARCHAR(255) NOT NULL,
    smtp_port INTEGER NOT NULL DEFAULT 587,
    smtp_user VARCHAR(100),
    smtp_password_encrypted TEXT,
    from_email VARCHAR(100) NOT NULL,
    use_tls BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Frontend Modules table
CREATE TABLE IF NOT EXISTS frontend_modules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    module_key VARCHAR(50) NOT NULL UNIQUE,
    module_name VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    roles_allowed TEXT[],
    config JSONB,
    sort_order INTEGER DEFAULT 0,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Storage Configs table
CREATE TABLE IF NOT EXISTS storage_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(50) NOT NULL UNIQUE,
    directory_path VARCHAR(500) NOT NULL,
    description TEXT,
    max_size_mb INTEGER,
    retention_days INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI Usage Logs table
CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    provider_id UUID REFERENCES ai_providers(id),
    model_id UUID REFERENCES ai_models(id),
    task_id UUID REFERENCES analysis_tasks(id),
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost TEXT,
    request_duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ai_usage_created ON ai_usage_logs(created_at);

-- Insert default departments
INSERT INTO departments (name, description) VALUES
    ('Network Team', 'Network device management team'),
    ('Server Team', 'Server infrastructure team'),
    ('K8S Team', 'Kubernetes cluster management team'),
    ('Audit Team', 'Security and compliance audit team'),
    ('IT Admin', 'IT administration team')
ON CONFLICT (name) DO NOTHING;

-- Insert default scheduled tasks
INSERT INTO scheduled_tasks (name, task_type, cron_expression, is_active) VALUES
    ('Daily Report', 'daily_report', '0 8 * * *', TRUE),
    ('Auto Analysis', 'auto_analysis', '0 */6 * * *', TRUE),
    ('Log Cleanup', 'log_cleanup', '0 0 * * 0', FALSE)
ON CONFLICT DO NOTHING;

-- Insert default frontend modules
INSERT INTO frontend_modules (module_key, module_name, is_enabled, sort_order) VALUES
    ('dashboard', 'Dashboard', TRUE, 1),
    ('logs', 'Log Query', TRUE, 2),
    ('analysis', 'AI Analysis', TRUE, 3),
    ('reports', 'Reports', TRUE, 4),
    ('charts', 'Charts', TRUE, 5),
    ('profile', 'Profile', TRUE, 6)
ON CONFLICT (module_key) DO NOTHING;

-- Insert default storage configs
INSERT INTO storage_configs (config_key, directory_path, description, retention_days) VALUES
    ('raw_logs', '/data/raw', 'Raw ELK log files', NULL),
    ('parsed_logs', '/data/parsed', 'Parsed and structured logs', NULL),
    ('reports', '/data/reports', 'Analysis reports', NULL),
    ('audit', '/data/audit', 'Audit logs', NULL)
ON CONFLICT (config_key) DO NOTHING;