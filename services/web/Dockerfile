# EA Explorer web image (ours): React build served by unprivileged nginx on port 8080
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV NGINX_ENVSUBST_FILTER="^EAX_"
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
