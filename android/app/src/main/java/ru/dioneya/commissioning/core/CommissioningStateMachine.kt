package ru.dioneya.commissioning.core

enum class CommissioningState {
    IDLE,
    SCANNING,
    CONNECTING,
    AUTHENTICATING,
    READY,
    CONFIGURING,
    DIAGNOSTICS,
    OTA,
    VERIFYING,
    REBOOT_WAIT,
    CONFIRMED,
    ROLLED_BACK,
    FAILED,
}

class CommissioningStateMachine(initial: CommissioningState = CommissioningState.IDLE) {
    var state: CommissioningState = initial
        private set

    fun transition(next: CommissioningState) {
        require(next in allowed.getValue(state)) { "invalid transition: $state -> $next" }
        state = next
    }

    companion object {
        private val terminal = setOf(CommissioningState.IDLE)
        private val failure = setOf(CommissioningState.FAILED)
        private val allowed = mapOf(
            CommissioningState.IDLE to setOf(CommissioningState.SCANNING),
            CommissioningState.SCANNING to setOf(CommissioningState.CONNECTING, CommissioningState.IDLE, CommissioningState.FAILED),
            CommissioningState.CONNECTING to setOf(CommissioningState.AUTHENTICATING, CommissioningState.IDLE, CommissioningState.FAILED),
            CommissioningState.AUTHENTICATING to setOf(CommissioningState.READY, CommissioningState.IDLE, CommissioningState.FAILED),
            CommissioningState.READY to setOf(CommissioningState.CONFIGURING, CommissioningState.DIAGNOSTICS, CommissioningState.OTA, CommissioningState.IDLE),
            CommissioningState.CONFIGURING to setOf(CommissioningState.READY, CommissioningState.FAILED),
            CommissioningState.DIAGNOSTICS to setOf(CommissioningState.READY, CommissioningState.FAILED),
            CommissioningState.OTA to setOf(CommissioningState.VERIFYING, CommissioningState.FAILED),
            CommissioningState.VERIFYING to setOf(CommissioningState.REBOOT_WAIT, CommissioningState.FAILED),
            CommissioningState.REBOOT_WAIT to setOf(CommissioningState.CONFIRMED, CommissioningState.ROLLED_BACK, CommissioningState.FAILED),
            CommissioningState.CONFIRMED to terminal,
            CommissioningState.ROLLED_BACK to terminal,
            CommissioningState.FAILED to failure + CommissioningState.IDLE,
        )
    }
}
