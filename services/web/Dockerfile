# EA Explorer web image (ours): React build served by unprivileged nginx on port 8080
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# the Alpine packages' own fixes (OpenSSL, brotli: R2.24), then back to the image's unprivileged user
USER root
RUN apk upgrade --no-cache
USER 101
ENV NGINX_ENVSUBST_FILTER="^EAX_"
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
# the npm packages the screens were built from (not served): image scans (Trivy, phase 36.1) read them here
COPY --from=build /src/package.json /src/package-lock.json /usr/share/eax-web-build/
EXPOSE 8080
