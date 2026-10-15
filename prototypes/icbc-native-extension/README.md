# Chrome 填写执行器

包版本1.3.9，注入核心1.2.36，客户端1.2.13，协议v1。目录名保留历史兼容；当前包含通用控件层及专用适配器，不局限于目录名对应的平台。

Chrome 加载已解压目录，首次授予 HTTPS 权限，之后从本机工作台“开始投递”自动连接，无需逐次点插件。详情见 [安装](../../docs/SETUP.md)。调试弹窗不是正式申请入口。

`background.js`、`service-controller.js` 负责单后台控制与官网标签复用；`client.js` 限定当前目标注入；`executor-core.js` 处理协议与执行锁；`generic-adapter.js`、专用 adapter 处理控件；`material-runner.js` 调度材料、原件、草稿和重新打开核对。

[API](API.md) · [类型](protocol.d.ts) · [测试](../../docs/TESTING.md)。未支持控件、未知事实、保存失败如实报告；不勾协议、不处理登录或最终提交。版本更新后需在 Chrome 重新加载，不能凭源码版本推断浏览器实际运行版本。
