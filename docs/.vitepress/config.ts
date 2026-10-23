import { defineConfig } from 'vitepress'

const repo = 'https://github.com/lxfight/astrbot_plugin_mnemosyne'

const zhGuide = [
  { text: '快速开始', link: '/guide/getting-started' },
  { text: '配置说明', link: '/guide/configuration' },
  { text: '数据库选择', link: '/guide/database' },
  { text: '性能调优', link: '/guide/performance' },
  { text: '命令与管理', link: '/guide/commands' }
]

const enGuide = [
  { text: 'Getting Started', link: '/en/guide/getting-started' },
  { text: 'Configuration', link: '/en/guide/configuration' },
  { text: 'Database Options', link: '/en/guide/database' },
  { text: 'Performance', link: '/en/guide/performance' },
  { text: 'Commands and Admin', link: '/en/guide/commands' }
]

export default defineConfig({
  title: 'Mnemosyne',
  description: 'AstrBot long-term memory plugin',
  lastUpdated: true,
  cleanUrls: true,
  markdown: {
    lineNumbers: true
  },
  themeConfig: {
    logo: '/mnemosyne-mark.svg',
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
          { text: '数据库', link: '/guide/database' },
          { text: 'GitHub', link: repo }
        ],
        sidebar: [
          {
            text: '使用指南',
            items: zhGuide
          },
          {
            text: '参考',
            items: [{ text: '故障排查', link: '/reference/troubleshooting' }]
          }
        ],
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
          { text: 'Databases', link: '/en/guide/database' },
          { text: 'GitHub', link: repo }
        ],
        sidebar: [
          {
            text: 'Guide',
            items: enGuide
          },
          {
            text: 'Reference',
            items: [{ text: 'Troubleshooting', link: '/en/reference/troubleshooting' }]
          }
        ],
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
