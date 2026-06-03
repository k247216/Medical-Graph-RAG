# 项目结构说明

  ## frontend

  前端目录是一个基于 Vue 3 + Vite
  的单页应用，用于承载医学图谱检索和诊断建议相关页面。

  frontend/
  ├── public/              # 静态资源目录
  ├── src/                 # 前端源码
  │   ├── assets/          # 图片、图标等资源
  │   ├── components/      # Vue 组件
  │   ├── App.vue          # 根组件
  │   ├── main.js          # 应用入口，挂载 Vue 应用
  │   └── style.css        # 全局样式
  ├── index.html           # Vite 页面入口
  ├── package.json         # 前端依赖和脚本配置
  ├── package-lock.json    # 依赖锁定文件
  └── vite.config.js       # Vite 构建配置

  **主要职责：**

  - 提供用户交互界面
  - 通过接口调用后端服务
  - 展示图谱查询结果、诊断建议和诊断链路

  ## Medical-Graph-RAG/backend

  后端目录是基于 FastAPI
  的服务层，负责对外提供健康检查、图谱检索和诊断建议接口。

  Medical-Graph-RAG/backend/
  ├── services/                # 业务服务模块
  │   ├── chain_builder.py     # 构建诊断链路数据
  │   ├── context_builder.py   # 将图谱结果整理为 LLM 上下文
  │   ├── diagnosis_service.py # 诊断建议业务编排
  │   ├── graph_service.py     # Neo4j 图谱查询服务
  │   └── llm_service.py       # 大模型调用服务
  ├── app.py                   # FastAPI 应用入口和接口定义
  ├── config.py                # 配置读取
  ├── deps.py                  # 依赖注入
  ├── schemas.py               # 请求和响应数据模型
  ├── requirements.txt         # 后端 Python 依赖
  ├── .env.example             # 环境变量示例
  └── init.py              # Python 包标识

  **主要接口：**

  | 接口 | 说明 |
  |------|------|
  | `GET /api/health` | 检查 Neo4j 和大模型服务状态 |
  | `POST /api/graph/search` | 根据关键词查询医学知识图谱子图 |
  | `POST /api/diagnosis/suggestions` |
  结合患者信息、关键词和图谱上下文生成诊断建议，并返回诊断链 |

  **整体调用流程：**

  前端输入患者信息和关键词
          ↓
  FastAPI 后端接收请求
          ↓
  GraphService 查询 Neo4j 医学图谱
          ↓
  ContextBuilder 整理图谱上下文
          ↓
  LlmService 生成诊断建议
          ↓
  ChainBuilder 构建诊断链
          ↓
  前端展示诊断建议和推理路径
  ```
