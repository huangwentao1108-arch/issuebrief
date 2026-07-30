# issuebrief

[![CI](https://github.com/huangwentao1108-arch/issuebrief/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/huangwentao1108-arch/issuebrief/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/issuebrief.svg)](https://pypi.org/project/issuebrief/)
[![Python](https://img.shields.io/pypi/pyversions/issuebrief.svg)](https://pypi.org/project/issuebrief/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

将命令输出生成可用于 GitHub Issue 的 Markdown 报告，并在本地进行尽力而为的脱敏。

**分享前必须由人工逐字复核生成的报告。** 脱敏基于规则，不能保证删除所有密钥、个人信息或敏感路径。

[English README](README.md)

## 30 秒上手

```console
# v0.1.1 发布工作流成功发布到 PyPI 后：
python -m pip install "issuebrief==0.1.1"

# PyPI 发布成功前，请从对应版本标签安装：
python -m pip install "git+https://github.com/huangwentao1108-arch/issuebrief.git@v0.1.1"
issuebrief run --output issue.md -- python -m your_package --diagnose
```

打开 `issue.md`，确认不存在敏感内容后，再将它粘贴到 GitHub Issue。

`issuebrief` 不会发送命令输出：没有联网、没有账号、没有遥测、没有后台服务。它只执行你明确指定的命令，并写入你指定的本地报告。

## 命令

### 运行并生成报告

```console
issuebrief run [--output PATH] [--timeout SECONDS] [--no-system-info] -- COMMAND...
```

命令不会经由 shell 执行。标准输出、标准错误、展示的命令行及当前用户的主目录路径会先经过内置脱敏器，再写入 Markdown。

```console
# 默认输出 issue-report.md
issuebrief run -- python -m pip --version

# 10 秒后停止子进程
issuebrief run --timeout 10 --output diagnostics.md -- your-command --flag

# 不写入操作系统与 Python 版本
issuebrief run --no-system-info -- your-command
```

报告包含命令、状态、退出码、耗时、脱敏后的工作目录、可选系统信息、脱敏后的 stdout/stderr 及替换计数。

### 报告示例

```markdown
# Issue Brief

## Result

- Status: completed
- Exit code: 2
- Duration: 0.055s

## Standard Error

    configuration invalid

## Redaction

- HOME_PATH: 1
```

### 脱敏已有文本

```console
issuebrief sanitize [FILE|-]
```

省略参数（或使用 `-`）时，从标准输入读取并输出脱敏文本：

```console
issuebrief sanitize app.log > app-sanitized.log
some-command 2>&1 | issuebrief sanitize
```

## 退出码

`run` 在命令正常结束时返回子进程的退出码；超时返回 `124`；命令无法启动返回 `127`。参数、读取和写入错误会显示 CLI 错误并以非零码退出。`sanitize` 成功输出时返回 `0`。

## 脱敏范围与限制

内置规则尝试识别常见凭据（GitHub 风格 token、Bearer 凭据、私钥块、常见 API key 赋值、带密码的 URL）、邮箱、主目录路径和非回环 IPv4 地址。替换内容会清晰显示，例如 `[REDACTED:GITHUB_TOKEN]`。

这是小而确定的第一道检查，不是安全边界，也不是完整的密钥扫描器。自定义格式、编码值、可识别个人或公司的上下文，以及新型凭据都可能残留。不要为了制作报告而执行不受信任的命令；未经人工复核，绝不要公开报告。

## 环境与开发

- Python 3.10 或更高版本
- 无运行时联网、无第三方运行时依赖

`v0.1.1` 的发布工作流已配置 PyPI 可信发布。该工作流成功完成前，
不能假定 `issuebrief==0.1.1` 已在 PyPI 可用；此前请使用上方的版本化源码标签。

在源码目录运行标准库测试：

```console
python -m pip install -e ".[dev]"
ruff check src tests
ruff format --check src tests
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题见 [SECURITY.md](SECURITY.md)，版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
