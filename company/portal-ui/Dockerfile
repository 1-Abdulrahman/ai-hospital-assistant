FROM node:24.13.1-alpine AS build
WORKDIR /ui

# Copy offline npm cache from repo root
COPY docs/offline/npm-cache /npm-cache

# Copy only dependency manifests first for better layer caching
COPY company/portal-ui/package.json company/portal-ui/package-lock.json ./

# Deterministic install, should not hit the internet if cache is complete
RUN npm ci --cache /npm-cache --prefer-offline --no-audit --no-fund

# Copy app source
COPY company/portal-ui/ ./

RUN npm run build

FROM nginx:1.27.4-alpine


COPY company/portal-ui/nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /ui/dist /usr/share/nginx/html
EXPOSE 80
