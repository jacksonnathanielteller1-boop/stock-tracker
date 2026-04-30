/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.plugins.push(
        new (require('webpack').IgnorePlugin)({
          resourceRegExp: /^@gadicc\/fetch-mock-cache/,
        })
      )
    }
    return config
  },
}

module.exports = nextConfig
