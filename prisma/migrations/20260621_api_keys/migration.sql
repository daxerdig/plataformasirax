-- Sirax · API Keys & Request Logs
-- Migración: tablas para la API pública /v1

CREATE TABLE "ApiKey" (
    "id"          TEXT NOT NULL,
    "userId"      TEXT NOT NULL,
    "name"        TEXT NOT NULL,
    "keyHash"     TEXT NOT NULL,
    "keyPrefix"   TEXT NOT NULL,
    "scopes"      TEXT NOT NULL DEFAULT '*',
    "rateLimit"   INTEGER NOT NULL DEFAULT 1000,
    "usageCount"  INTEGER NOT NULL DEFAULT 0,
    "lastUsedAt"  TIMESTAMP(3),
    "expiresAt"   TIMESTAMP(3),
    "active"      BOOLEAN NOT NULL DEFAULT true,
    "createdAt"   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ApiKey_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ApiKey_keyHash_key" ON "ApiKey"("keyHash");
CREATE INDEX "ApiKey_userId_idx"  ON "ApiKey"("userId");

CREATE TABLE "ApiRequestLog" (
    "id"          TEXT NOT NULL,
    "apiKeyId"    TEXT NOT NULL,
    "endpoint"    TEXT NOT NULL,
    "method"      TEXT NOT NULL,
    "statusCode"  INTEGER NOT NULL,
    "durationMs"  INTEGER NOT NULL,
    "ip"          TEXT,
    "createdAt"   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ApiRequestLog_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "ApiRequestLog_apiKeyId_idx" ON "ApiRequestLog"("apiKeyId");
CREATE INDEX "ApiRequestLog_createdAt_idx" ON "ApiRequestLog"("createdAt");

ALTER TABLE "ApiKey" ADD CONSTRAINT "ApiKey_userId_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
