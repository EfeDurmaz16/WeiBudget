# WeiBudget

An owner gives one agent a daily ETH allowance. The [reference wallet](src/wallet.fe) charges the allowance and sends the payment in one EVM transaction. If the recipient rejects the payment, the agent keeps its unused allowance. If the owner revokes and restores the limit that day, any successful payments still count.

## Try it

From a checkout on macOS or Linux (ARM64 or x86-64), with Python 3.9 or newer:

```sh
./demo
```

The launcher uses Fe 26.6.0 and Anvil 1.7.1. If a matching tool is missing, it downloads the official release, verifies its SHA-256 digest and installs it under `.tools/` in this checkout. The first run needs network access for missing tools. The demo starts a disposable local chain. It checks transaction receipts, ETH balances and the remaining allowance through the public ABI.

Each row below shows the on-chain state after the action, in wei. The wallet starts with 20 wei and a daily limit of 10.

| Action | Wallet balance | Recipient balance | Rejecting contract balance | Available allowance |
| --- | ---: | ---: | ---: | ---: |
| Grant 10 | 20 | 0 | 0 | 10 |
| Pay the recipient 6 | 14 | 6 | 0 | 4 |
| Try paying the rejecting contract 3 | 14 | 6 | 0 | 4 |
| Revoke the allowance | 14 | 6 | 0 | 0 |
| Try paying the original recipient 1 | 14 | 6 | 0 | 0 |
| Restore the 10 wei limit on the same day | 14 | 6 | 0 | 4 |

The demo then uses the remaining 4 wei, checks that the next wei is denied, and pays again after the next UTC midnight. The recipient never submits a transaction, so gas fees do not affect its balance.

## How it works

[The Fe source](src/lib.fe) exposes three pure functions. `utc_day` maps a typed `Timestamp` to a calendar day. `remaining_at` calculates headroom from the daily limit and the last recorded spend. `charge_at` checks a positive charge against that headroom before adding it to the day's spend. This order handles a full-width `uint256` allowance safely.

The contract stores the owner, agent, daily limit, last spending day and amount spent. Its constructor takes the agent address and records the deployer as owner. The initial limit is zero. Fe's `Ctx` effect supplies the caller and block timestamp. Amounts stay typed as `Wei` until the ABI boundary. Each message declares which storage fields it can read or mutate.

| Contract call | Caller | Behavior |
| --- | --- | --- |
| `setLimit(uint256)` | Owner | Sets the daily cap. Preserves spend already recorded for today. |
| `revoke()` | Owner | Sets the cap to zero. It stays zero across day boundaries until the owner grants a new limit. |
| `consume(uint256)` | Agent | Records a positive charge or reverts. Returns the remaining allowance. |
| `remaining()` | Anyone | Reads the allowance available at the current block timestamp. |

**Wallet integration.** The example wallet holds the local test ETH. It deploys its own WeiBudget policy and sets the wallet's address as the authorized caller of `consume`. The owner sets or revokes the limit through the wallet. The appointed agent calls `pay`. The wallet checks the caller, charges the policy, then sends the value. A failed value transfer reverts the whole transaction, including the charge recorded in the separate policy contract.

The wallet is a local reference implementation with one payment entry point and no owner recovery or withdrawal flow. Use disposable test funds. Each instance has one fixed owner and agent. A new calendar day starts at 00:00 UTC according to block time. Two spends on opposite sides of midnight can each use a full day's allowance. Reducing the limit below what was already used gives zero headroom. Transactions mined before revocation retain their effect.

## Build and test

After running the demo, the following commands use the same Fe release. The build writes the contract ABI and creation bytecode under `out/`.

```sh
export PATH="$PWD/.tools:$PATH"
fe --version
fe fmt --check
fe test
fe build --contract WeiBudget --emit abi,bytecode
fe build --contract ReferenceWallet --emit abi,bytecode
```

[The Fe tests](src/tests.fe) cover distinct owner and agent callers, a disabled grant, an invalid agent address, exact and over-limit charges, same-day limit changes, revocation and regrant, UTC rollover, and arithmetic at the maximum allowance. The [wallet tests](src/wallet_tests.fe) check role separation, balance changes, transfer rollback, and a successful payment of the same size as a rejected one. The [demo runner](scripts/run-demo.py) exercises the public ABI on Anvil.

## Contest entry and disclosures

WeiBudget was built during the November 2026 Fe Builders Challenge. Efe Baran Durmaz selected the project, the daily-limit and revocation behavior, and the local-demo scope. Codex assisted with the implementation, tests, demo, CI, documentation and verification.

The [contest starter](https://github.com/fe-lang/builders-challenge-starter/tree/f9d9aa92a03af82c2bbb0dc2e0810244eb13e686) served as a reference for Fe syntax, typed EVM calls and compiler commands. The allowance policy, contract, scenarios and demo were written for this entry. The demo uses the upstream Fe compiler and Foundry's Anvil. Project code is available under the [MIT license](LICENSE).
