---
document_id: security-account-access
title: 系统账号与数据访问管理规范
document_type: handbook
department: security
visibility: department
allowed_roles:
  - department_admin
  - knowledge_admin
version: "1.0"
status: active
effective_from: "2026-03-15T00:00:00+08:00"
effective_to: null
supersedes_id: null
source_path: security/account-access-policy.md
---

# 系统账号与数据访问管理规范

## 最小权限

账号权限应与岗位职责匹配，申请人不得为自己审批权限。部门管理员只能审批本部门业务系统的普通权限。

## 账号生命周期

员工转岗时，原部门权限应在转岗生效日结束前回收，新部门权限在直属负责人确认后申请。

## 安全事件

发现账号异常登录或凭据泄露时，应立即暂停相关会话并通过安全事件入口报送，不得在群聊中传播凭据。

