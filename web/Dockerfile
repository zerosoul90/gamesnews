# Build stage
FROM node:20-alpine AS build
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci

# Copy source code and build
COPY . .
# Sử dụng cấu hình development để apiUrl trỏ về http://localhost:8000 thay vì /api
RUN npm run build -- --configuration development

# Run stage
FROM node:20-alpine
WORKDIR /app

# Copy the built artifacts from the build stage
COPY --from=build /app/dist /app/dist
COPY package.json ./

EXPOSE 4000
CMD ["npm", "run", "serve:ssr:web"]
