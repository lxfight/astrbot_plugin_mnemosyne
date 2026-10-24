import { defineConfig } from 'vitepress'

const repo = 'https://github.com/lxfight/astrbot_plugin_mnemosyne'
const siteUrl = 'https://lxfight.github.io/astrbot_plugin_mnemosyne/'
const base = (process.env.DOCS_BASE || '/').replace(/\/?$/, '/')

const zhGuide = [
  { text: '快速开始', link: '/guide/getting-started' },
  { text: '配置说明', link: '/guide/configuration' },
  { text: '数据库选择', link: '/guide/database' }
]

const zhOperations = [
  { text: '管理面板', link: '/guide/admin-panel' },
  { text: '命令与管理', link: '/guide/commands' },
  { text: '性能调优', link: '/guide/performance' }
]

const zhReference = [
  { text: '架构与数据流', link: '/reference/architecture' },
  { text: '本地开发与部署', link: '/reference/development' },
  { text: '故障排查', link: '/reference/troubleshooting' }
]

const enGuide = [
  { text: 'Getting Started', link: '/en/guide/getting-started' },
  { text: 'Configuration', link: '/en/guide/configuration' },
  { text: 'Database Options', link: '/en/guide/database' }
]

const enOperations = [
  { text: 'Admin Panel', link: '/en/guide/admin-panel' },
  { text: 'Commands and Admin', link: '/en/guide/commands' },
  { text: 'Performance', link: '/en/guide/performance' }
]

const enReference = [
  { text: 'Architecture', link: '/en/reference/architecture' },
  { text: 'Development and Deployment', link: '/en/reference/development' },
  { text: 'Troubleshooting', link: '/en/reference/troubleshooting' }
]

export default defineConfig({
  base,
  title: 'Mnemosyne',
  description: 'AstrBot 长期记忆插件：可检索、可管理、可迁移的 RAG 记忆层。',
  lang: 'zh-CN',
  lastUpdated: true,
  cleanUrls: true,
  sitemap: {
    hostname: siteUrl
  },
  head: [
    [
      'link',
      {
        rel: 'icon',
        type: 'image/svg+xml',
        href: `${base}mnemosyne-mark.svg`
      }
    ],
    ['meta', { name: 'theme-color', content: '#2f6f68' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'Mnemosyne' }],
    ['meta', { property: 'og:title', content: 'Mnemosyne 文档' }],
    [
      'meta',
      {
        property: 'og:description',
        content: 'AstrBot 长期记忆插件的安装、配置、运维与架构文档。'
      }
    ],
    ['meta', { property: 'og:url', content: siteUrl }],
    ['meta', { property: 'og:image', content: `${siteUrl}mnemosyne-mark.svg` }]
  ],
  markdown: {
    lineNumbers: true
  },
  themeConfig: {
    logo: '/mnemosyne-mark.svg',
    siteTitle: 'Mnemosyne',
    socialLinks: [{ icon: 'github', link: repo }],
    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: {
                buttonText: '搜索',
                buttonAriaLabel: '搜索文档'
              },
              modal: {
                displayDetails: '显示详细列表',
                resetButtonTitle: '重置搜索',
                backButtonTitle: '关闭搜索',
                noResultsText: '没有找到结果',
                footer: {
                  selectText: '选择',
                  selectKeyAriaLabel: '回车',
                  navigateText: '导航',
                  navigateUpKeyAriaLabel: '向上',
                  navigateDownKeyAriaLabel: '向下',
                  closeText: '关闭',
                  closeKeyAriaLabel: 'Esc'
                }
              }
            }
          }
        }
      }
    }
  },
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      title: 'Mnemosyne',
      description: 'AstrBot 长期记忆插件',
      themeConfig: {
        nav: [
          { text: '指南', link: '/guide/getting-started' },
          { text: '管理面板', link: '/guide/admin-panel' },
          { text: '架构', link: '/reference/architecture' },
          { text: 'GitHub', link: repo }
        ],
        sidebar: [
          {
            text: '开始使用',
            items: zhGuide
          },
          {
            text: '使用与运维',
            items: zhOperations
          },
          {
            text: '参考',
            items: zhReference
          }
        ],
        editLink: {
          pattern: `${repo}/edit/main/docs/:path`,
          text: '在 GitHub 编辑此页'
        },
        footer: {
          message: '基于 RAG 的 AstrBot 长期记忆插件',
          copyright: 'Copyright © 2026 lxfight · 自定义许可证'
        },
        outline: {
          label: '本页目录',
          level: [2, 3]
        },
        docFooter: {
          prev: '上一页',
          next: '下一页'
        },
        lastUpdated: {
          text: '最后更新'
        },
        langMenuLabel: '切换语言',
        sidebarMenuLabel: '菜单',
        returnToTopLabel: '回到顶部',
        darkModeSwitchLabel: '外观'
      }
    },
    en: {
      label: 'English',
      lang: 'en-US',
      title: 'Mnemosyne',
      description: 'Long-term memory plugin for AstrBot',
      themeConfig: {
        nav: [
          { text: 'Guide', link: '/en/guide/getting-started' },
          { text: 'Admin Panel', link: '/en/guide/admin-panel' },
          { text: 'Architecture', link: '/en/reference/architecture' },
          { text: 'GitHub', link: repo }
        ],
        sidebar: [
          {
            text: 'Get Started',
            items: enGuide
          },
          {
            text: 'Operations',
            items: enOperations
          },
          {
            text: 'Reference',
            items: enReference
          }
        ],
        editLink: {
          pattern: `${repo}/edit/main/docs/:path`,
          text: 'Edit this page on GitHub'
        },
        footer: {
          message: 'A RAG-based long-term memory layer for AstrBot',
          copyright: 'Copyright © 2026 lxfight · Custom license'
        },
        outline: {
          label: 'On This Page',
          level: [2, 3]
        },
        docFooter: {
          prev: 'Previous',
          next: 'Next'
        },
        lastUpdated: {
          text: 'Last updated'
        }
      }
    }
  }
})
