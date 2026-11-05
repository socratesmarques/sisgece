FROM node:22-bookworm-slim

ENV NODE_ENV=production

WORKDIR /app/backend

# Instala dependências antes do código para aproveitar o cache de build.
COPY backend/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY backend/ ./
COPY frontend/ /app/frontend/

# O servidor não precisa executar como root.
USER node

EXPOSE 3000
CMD ["node", "app.js"]
