FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build
CMD ["npx", "--no-install", "vite", "preview", "--host", "0.0.0.0", "--port", "5173"]
