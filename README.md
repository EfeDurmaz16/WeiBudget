# WeiBudget

An owner gives one agent a daily allowance in wei and can revoke it in one call. If the owner restores the allowance later that day, the agent can use only what it had left. WeiBudget implements this rule as a small Fe library and an EVM contract.

## Try it

From a checkout on macOS or Linux (ARM64 or x86-64), with Python 3.9 or newer:

```sh
./demo
```

The launcher uses Fe 26.6.0 and Anvil 1.7.1. If a matching tool is missing, it downloads the official release, verifies its SHA-256 digest and installs it under `.tools/` in this checkout. The first run needs network access for missing tools. The demo starts its own disposable local chain with two temporary accounts. It reads each result from the deployed contract and checks the receipt of each transaction.

| Action | Remaining |
| --- | ---: |
| Owner grants 10 wei per UTC day | 10 |
| Agent consumes 6, then 4 | 4, then 0 |
| Agent tries one more wei | 0, transaction reverts |
| First block of the next UTC day | 10 |
| Agent consumes 3 | 7 |
| Owner revokes and the agent tries to consume 1 | 0, transaction reverts |
| Owner restores the 10 wei limit that day | 7 |

## How it works

[The Fe source](src/lib.fe) exposes three pure functions. `utc_day` maps a typed `Timestamp` to a calendar day. `remaining_at` calculates headroom from the daily limit and the last recorded spend. `charge_at` checks a positive charge against that headroom before adding it to the day's spend. This order handles a full-width `uint256` allowance safely.

The contract stores the owner, agent, daily limit, last spending day and amount spent. Its constructor takes the agent address and records the deployer as owner. The initial limit is zero. Fe's `Ctx` effect supplies the caller and block timestamp. Amounts stay typed as `Wei` until the ABI boundary. Each message declares which storage fields it can read or mutate.

| Contract call | Caller | Behavior |
| --- | --- | --- |
| `setLimit(uint256)` | Owner | Sets the daily cap. Preserves spend already recorded for today. |
| `revoke()` | Owner | Sets the cap to zero. It stays zero across day boundaries until the owner grants a new limit. |
| `consume(uint256)` | Agent | Records a positive charge or reverts. Returns the remaining allowance. |
| `remaining()` | Anyone | Reads the allowance available at the current block timestamp. |

**Integration boundary.** WeiBudget accounts for authorized wei. It holds no funds and makes no transfers. A wallet integrating the contract can use its own executor address as the designated agent, call `consume` before transferring ETH, and revert the whole transaction if the transfer fails. Every spend path covered by the wallet's policy must use that check.

Each instance has one fixed owner and agent. A new calendar day starts at 00:00 UTC according to block time. Two spends on opposite sides of midnight can each use a full day's allowance. Reducing the limit below what was already used gives zero headroom. Transactions mined before revocation retain their effect.

## Build and test

After running the demo, the following commands use the same Fe release. The build writes the contract ABI and creation bytecode under `out/`.

```sh
export PATH="$PWD/.tools:$PATH"
fe --version
fe fmt --check
fe test
fe build --contract WeiBudget --emit abi,bytecode
```

[The Fe tests](src/tests.fe) cover distinct owner and agent callers, a disabled grant, an invalid agent address, exact and over-limit charges, same-day limit changes, revocation and regrant, UTC rollover, and arithmetic at the maximum allowance. The [demo runner](scripts/run-demo.py) exercises the public ABI on Anvil.

## Contest entry and disclosures

WeiBudget was built during the November 2026 Fe Builders Challenge. Efe Baran Durmaz selected the project, the daily-limit and revocation behavior, and the local-demo scope. Codex assisted with the implementation, tests, demo, CI, documentation and verification.

The [contest starter](https://github.com/fe-lang/builders-challenge-starter/tree/f9d9aa92a03af82c2bbb0dc2e0810244eb13e686) served as a reference for Fe syntax, typed EVM calls and compiler commands. The allowance policy, contract, scenarios and demo were written for this entry. The demo uses the upstream Fe compiler and Foundry's Anvil. Project code is available under the [MIT license](LICENSE).
