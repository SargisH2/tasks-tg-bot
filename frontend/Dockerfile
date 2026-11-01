FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WS_URL=/ws/tasks
ARG VITE_TELEGRAM_BOT_USERNAME=YourTaskBot
ARG VITE_ALLOW_DEV_AUTH=true

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_URL=${VITE_WS_URL}
ENV VITE_TELEGRAM_BOT_USERNAME=${VITE_TELEGRAM_BOT_USERNAME}
ENV VITE_ALLOW_DEV_AUTH=${VITE_ALLOW_DEV_AUTH}

COPY package.json /app/package.json
RUN npm install

COPY . /app
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
