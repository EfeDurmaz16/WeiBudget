#!/usr/bin/env python3
"""Run the WeiBudget contract against a disposable local Anvil instance."""

import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = 86_400
MIDNIGHT = 20_000 * DAY


def demonstrate(ipc, bytecode):
    def rpc(method, *params):
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(5)
            client.connect(str(ipc))
            client.sendall(json.dumps(request).encode() + b"\n")
            with client.makefile("rb") as stream:
                response = json.loads(stream.readline())
        if "error" in response:
            raise RuntimeError(f"{method}: {response['error']}")
        return response["result"]

    def calldata(signature, *arguments):
        selector = rpc("web3_sha3", "0x" + signature.encode().hex())[:10]
        return selector + "".join(f"{value:064x}" for value in arguments)

    def transact(sender, data, *, to=None, expect_success=True):
        tx = {"from": sender, "data": data, "gas": hex(2_000_000)}
        if to:
            tx["to"] = to
        tx_hash = rpc("eth_sendTransaction", tx)
        deadline = time.monotonic() + 10
        receipt = rpc("eth_getTransactionReceipt", tx_hash)
        while receipt is None:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Local Anvil did not mine {tx_hash}")
            time.sleep(0.05)
            receipt = rpc("eth_getTransactionReceipt", tx_hash)
        if (int(receipt["status"], 16) == 1) != expect_success:
            raise RuntimeError(f"Unexpected transaction receipt: {receipt}")
        return receipt

    owner, agent = rpc("eth_accounts")
    init_code = "0x" + bytecode.removeprefix("0x") + f"{int(agent, 16):064x}"
    budget = transact(owner, init_code)["contractAddress"]

    def check(label, expected):
        result = rpc("eth_call", {"to": budget, "data": calldata("remaining()")}, "latest")
        remaining = int(result, 16)
        if remaining != expected:
            raise RuntimeError(f"{label}: expected {expected} wei; read {remaining}")
        print(f"{label:<43} remaining = {remaining} wei")

    transact(owner, calldata("setLimit(uint256)", 10), to=budget)
    check("Owner grants a daily limit of 10 wei", 10)
    transact(agent, calldata("consume(uint256)", 6), to=budget)
    check("Agent consumes 6 wei", 4)
    transact(agent, calldata("consume(uint256)", 4), to=budget)
    check("Agent consumes the final 4 wei", 0)
    transact(agent, calldata("consume(uint256)", 1), to=budget, expect_success=False)
    check("One more wei reverts", 0)

    rpc("evm_setNextBlockTimestamp", MIDNIGHT + DAY)
    rpc("evm_mine")
    check("Next UTC midnight renews the limit", 10)
    transact(agent, calldata("consume(uint256)", 3), to=budget)
    check("Agent consumes 3 wei", 7)
    transact(owner, calldata("revoke()"), to=budget)
    check("Owner revokes the allowance", 0)
    transact(agent, calldata("consume(uint256)", 1), to=budget, expect_success=False)
    check("Agent charge after revocation reverts", 0)
    transact(owner, calldata("setLimit(uint256)", 10), to=budget)
    check("Same-day regrant preserves the 3 wei used", 7)


def main():
    # A short path keeps the Unix socket name below the macOS and Linux limits.
    with tempfile.TemporaryDirectory(prefix="weibudget-", dir="/tmp") as directory:
        temp = Path(directory)
        subprocess.run(
            ["fe", "build", "--contract", "WeiBudget", "--emit", "bytecode", "--out-dir", directory],
            cwd=ROOT, check=True,
        )
        ipc = temp / "anvil.ipc"
        command = [
            "anvil", "--host", "127.0.0.1", "--port", "0", "--ipc", str(ipc),
            "--mnemonic-random", "--accounts", "2", "--timestamp", str(MIDNIGHT + DAY // 2),
            "--quiet",
        ]
        with subprocess.Popen(command, cwd=temp, stdout=subprocess.DEVNULL) as chain:
            try:
                deadline = time.monotonic() + 10
                while not ipc.exists():
                    if chain.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Local Anvil did not start")
                    time.sleep(0.05)
                demonstrate(ipc, (temp / "WeiBudget.bin").read_text().strip())
            finally:
                chain.terminate()


if __name__ == "__main__":
    main()
