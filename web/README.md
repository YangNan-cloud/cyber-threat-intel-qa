# Web 前端模块 - 威胁情报智能问答系统

## 模块职责

本模块负责系统的**用户交互界面与前端集成**，提供：
- 自然语言问题输入与威胁报告文件上传
- 调用后端问答服务（角色3）并展示结果
- 多轮对话支持与对话记录导出
- 系统评测结果可视化展示

## 目录结构
web/
├── components/
│ ├── app.py # Streamlit 主程序入口
│ ├── chat.py # 对话历史渲染组件
│ ├── evaluation.py # 评测结果展示组件
│ ├── ioc_display.py # IOC 列表展示组件
│ ├── sidebar.py # 侧边栏组件（对话历史列表、导出/清空）
├── utils/
│ ├── init.py
│ ├── api_client.py # 后端 API 调用封装
│ ├── file_parser.py # 上传文件解析（txt/docx/pdf）
│ ├── mock_response.py # 开发阶段 Mock 数据
│ └── session_manager.py # 多轮对话状态管理
└── README.md # 本文件

## 环境依赖
pip install -r requirements.txt

## 启动 Web 前端
```powershell
cd web
streamlit run app.py
```

## 后端接口对接
本模块通过 HTTP 调用兰书阳的问答服务：

接口地址 POST http://127.0.0.1:8000/api/chat

请求体:
```json
{"query": "问题", "top_k": 6, "conversation_id": "会话ID"}
```
响应体:
`answer`, `citations`, `entities`, `attribution`, `confidence`, `refusal`, `conversation_id`
