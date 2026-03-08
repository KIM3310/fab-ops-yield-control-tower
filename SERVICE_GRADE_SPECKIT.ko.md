# Service Grade Speckit

작성일: 2026-03-08

## 목표

이 repo는 semiconductor / industrial ops domain을 보여주기 위한 `control tower flagship`이다.

## 핵심 surface

- health
- runtime brief
- review pack
- alarm report schema
- shift handoff schema
- fab summary
- tool ownership
- alarm queue
- lot risk board
- release gate
- handoff signature
- audit feed
- replay evals

## 운영 원칙

- alarm severity가 queue ordering보다 먼저다
- lot risk는 release decision 전까지 visible 해야 한다
- release gate는 top lot에 대해 명시적인 decision을 보여줘야 한다
- handoff는 signed proof와 함께 다음 shift로 넘어가야 한다
- recommendations는 tool, lot, SOP context에 grounding 되어야 한다
- 다음 shift가 바로 읽을 수 있는 handoff surface가 필요하다
