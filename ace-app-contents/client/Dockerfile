# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM node:20-alpine3.19 AS build-env

RUN corepack enable
COPY ./bot-web-ui /app/

WORKDIR /app/client

RUN yarn install
RUN yarn build

# The `yarn install` above installs all the dependencies, including devDependencies.
# These devDependencies are only used to build the project, not to run it, so we do
# not want them in the final image. This makes the image lighter, and incidentally,
# reduces unnecessary warnings in vulnerability scans.
RUN rm -rf node_modules
RUN yarn workspaces focus --production # Like yarn install, but without devDependencies

FROM nvcr.io/nvidian/distroless/node:22-v3.0.4
COPY --from=build-env /app/client /app/client

# The env.js is used to inject environment variables in the client at startup time. It
# is edited by the entrypoint.js script. The script needs to be able to write the file,
# so we copy it with the --chown flag
COPY --from=build-env --chown=1000:1000 /app/client/dist/env.js /app/client/dist/env.js

WORKDIR /app/client/dist

# Copy the entrypoint script
COPY ./bot-web-ui/client/entrypoint.js /app/entrypoint.js

ENTRYPOINT ["node", "/app/entrypoint.js"]