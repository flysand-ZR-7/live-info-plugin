# Multi-stage lightweight Node.js container
FROM node:22-alpine AS builder

WORKDIR /app

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package descriptors
COPY package.json pnpm-lock.yaml* .npmrc* tsconfig.json ./

# Install dependencies and approve build scripts
RUN pnpm install --frozen-lockfile || pnpm install
RUN pnpm approve-builds --all

# Copy source code and build
COPY src ./src
COPY static ./static
COPY tools_manifest.json ./
RUN pnpm build

# Production runtime stage
FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8000
ENV HOST=0.0.0.0

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml* .npmrc* ./
RUN pnpm install --prod --frozen-lockfile || pnpm install --prod

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/static ./static
COPY --from=builder /app/tools_manifest.json ./

EXPOSE 8000

CMD ["node", "dist/index.js"]
