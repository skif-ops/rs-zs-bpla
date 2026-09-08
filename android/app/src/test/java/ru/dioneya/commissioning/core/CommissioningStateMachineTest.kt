package ru.dioneya.commissioning.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class CommissioningStateMachineTest {
    @Test
    fun validCommissioningPathReachesReady() {
        val machine = CommissioningStateMachine()
        machine.transition(CommissioningState.SCANNING)
        machine.transition(CommissioningState.CONNECTING)
        machine.transition(CommissioningState.AUTHENTICATING)
        machine.transition(CommissioningState.READY)
        assertEquals(CommissioningState.READY, machine.state)
    }

    @Test
    fun positionCommissioningCanReachFieldReady() {
        val machine = CommissioningStateMachine(CommissioningState.READY)
        machine.transition(CommissioningState.POSITIONING)
        machine.transition(CommissioningState.POSITION_VERIFYING)
        machine.transition(CommissioningState.DIAGNOSTICS)
        machine.transition(CommissioningState.FIELD_READY)
        assertEquals(CommissioningState.FIELD_READY, machine.state)
    }

    @Test
    fun cannotSkipAuthentication() {
        val machine = CommissioningStateMachine()
        assertThrows(IllegalArgumentException::class.java) {
            machine.transition(CommissioningState.READY)
        }
    }

    @Test
    fun cannotDeclareFieldReadyDirectlyFromReady() {
        val machine = CommissioningStateMachine(CommissioningState.READY)
        assertThrows(IllegalArgumentException::class.java) {
            machine.transition(CommissioningState.FIELD_READY)
        }
    }
}
