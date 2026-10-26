FROM node:22-bookworm-slim

WORKDIR /app

COPY backend/package*.json ./backend/

WORKDIR /app/backend

RUN npm ci --omit=dev

WORKDIR /app

COPY backend ./backend
COPY frontend ./frontend

WORKDIR /app/backend

EXPOSE 3000

CMD ["npm", "start"]
