-- Initial database schema for Smart Outfit Assistant
-- Version: 001
-- Description: Create users, user_profiles, and garments tables

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);

-- Create indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Create user_profiles table
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    height INTEGER NOT NULL CHECK (height >= 100 AND height <= 250),
    body_type VARCHAR(20) NOT NULL,
    skin_tone VARCHAR(20) NOT NULL,
    style_preference JSONB NOT NULL,
    budget_range VARCHAR(20) NOT NULL,
    avoid_body_parts JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create index for user_profiles table
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON user_profiles(user_id);

-- Create garments table
CREATE TABLE IF NOT EXISTS garments (
    garment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category VARCHAR(20) NOT NULL,
    main_color JSONB NOT NULL,
    secondary_colors JSONB DEFAULT '[]'::jsonb,
    style_tags JSONB DEFAULT '[]'::jsonb,
    fit_type VARCHAR(20),
    image_path VARCHAR(500) NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    feature_vector FLOAT8[] NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes for garments table
CREATE INDEX IF NOT EXISTS idx_garments_user_id ON garments(user_id);
CREATE INDEX IF NOT EXISTS idx_garments_category ON garments(category);
CREATE INDEX IF NOT EXISTS idx_garments_user_category ON garments(user_id, category);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers to automatically update updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_garments_updated_at BEFORE UPDATE ON garments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Optional: Create pgvector extension for vector similarity search (if available)
-- CREATE EXTENSION IF NOT EXISTS vector;
-- ALTER TABLE garments ADD COLUMN IF NOT EXISTS feature_vector_pgvector vector(1280);
-- CREATE INDEX IF NOT EXISTS idx_garments_feature_vector ON garments USING ivfflat (feature_vector_pgvector vector_cosine_ops);
