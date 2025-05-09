FROM node:18-alpine

WORKDIR /app

# Copy package files first
COPY package*.json ./
RUN npm ci --only=production

# Create secrets directory with correct permissions
RUN mkdir -p secrets && \
    chown node:node secrets && \
    chmod 700 secrets

# Copy service account files
COPY --chown=node:node serviceAccountKey.json serviceAccountKeyFirebase.json ./
RUN mv *.json secrets/ && \
    chown node:node secrets/*.json && \
    chmod 600 secrets/*.json

# Copy remaining files
COPY --chown=node:node . .

# Security hardening
RUN apk add --no-cache tini

USER node
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "server.js"]