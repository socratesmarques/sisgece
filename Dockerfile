FROM node:22-bookworm-slim

ENV NODE_ENV=production

WORKDIR /app/backend

# Instala dependências antes do código para aproveitar o cache de build.
COPY backend/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY backend/ ./
COPY frontend/pages/ /app/frontend/pages/
COPY frontend/assets/css/ /app/frontend/assets/css/
COPY frontend/assets/js/admin-login.js frontend/assets/js/admin-dashboard.js /app/frontend/assets/js/

# O servidor não precisa executar como root.
USER node

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/ready',{signal:AbortSignal.timeout(3000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

EXPOSE 3000
CMD ["node", "app.js"]
