package ru.dioneya.commissioning.core

enum class CommissioningState {
    IDLE,
    SCANNING,
    CONNECTING,
    AUTHENTICATING,
    READY,
    CONFIGURING,
    POSITIONING,
    POSITION_VERIFYING,
    DIAGNOSTICS,
    FIELD_READY,
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
            CommissioningState.READY to setOf(
                CommissioningState.CONFIGURING,
                CommissioningState.POSITIONING,
                CommissioningState.DIAGNOSTICS,
                CommissioningState.OTA,
                CommissioningState.IDLE,
            ),
            CommissioningState.CONFIGURING to setOf(CommissioningState.READY, CommissioningState.POSITIONING, CommissioningState.FAILED),
            CommissioningState.POSITIONING to setOf(CommissioningState.POSITION_VERIFYING, CommissioningState.READY, CommissioningState.FAILED),
            CommissioningState.POSITION_VERIFYING to setOf(CommissioningState.DIAGNOSTICS, CommissioningState.POSITIONING, CommissioningState.FAILED),
            CommissioningState.DIAGNOSTICS to setOf(CommissioningState.FIELD_READY, CommissioningState.READY, CommissioningState.FAILED),
            CommissioningState.FIELD_READY to setOf(CommissioningState.READY, CommissioningState.OTA, CommissioningState.IDLE),
            CommissioningState.OTA to setOf(CommissioningState.VERIFYING, CommissioningState.FAILED),
            CommissioningState.VERIFYING to setOf(CommissioningState.REBOOT_WAIT, CommissioningState.FAILED),
            CommissioningState.REBOOT_WAIT to setOf(CommissioningState.CONFIRMED, CommissioningState.ROLLED_BACK, CommissioningState.FAILED),
            CommissioningState.CONFIRMED to terminal,
            CommissioningState.ROLLED_BACK to terminal,
            CommissioningState.FAILED to failure + CommissioningState.IDLE,
        )
    }
}
