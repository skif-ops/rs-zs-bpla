#include "zs_dual_sim_bg95.h"

#include <ctype.h>
#include <string.h>

static bool action_is(const zs_dual_sim_t *controller,
                      zs_dual_sim_action_t expected) {
  return controller && zs_dual_sim_next_action(controller) == expected;
}

static bool full_iccid_available(const char *iccid) {
  size_t length;
  if (!iccid) return false;
  length = strlen(iccid);
  if (length < 18u || length > 22u) return false;
  for (size_t i = 0u; i < length; ++i) {
    if (!isdigit((unsigned char)iccid[i])) return false;
  }
  return true;
}

bool zs_dual_sim_bg95_begin_graceful_shutdown(zs_dual_sim_t *controller,
                                               zs_bg95_t *modem,
                                               uint32_t now_ms) {
  zs_bg95_shutdown_result_t result;
  if (!modem || !action_is(controller,
                           ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF))
    return false;
  result = zs_bg95_request_graceful_power_off(modem, now_ms);
  if (result == ZS_BG95_SHUTDOWN_REJECTED_BUSY) return false;
  if (result != ZS_BG95_SHUTDOWN_STARTED) {
    (void)zs_dual_sim_complete_action(
        controller, ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF, false, now_ms);
    return false;
  }
  return zs_dual_sim_complete_action(
      controller, ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF, true, now_ms);
}

bool zs_dual_sim_bg95_confirm_shutdown(zs_dual_sim_t *controller,
                                       zs_bg95_t *modem,
                                       bool cell_status_low,
                                       uint32_t now_ms) {
  if (!modem || !cell_status_low ||
      !action_is(controller, ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF) ||
      !zs_bg95_confirm_power_off(modem, true))
    return false;
  return zs_dual_sim_complete_action(
      controller, ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF, true, now_ms);
}

bool zs_dual_sim_bg95_begin_power_on(zs_dual_sim_t *controller,
                                     zs_bg95_t *modem,
                                     uint32_t now_ms) {
  if (!modem || !action_is(controller,
                           ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS))
    return false;
  zs_bg95_power_on(modem, now_ms);
  if (modem->state != ZS_BG95_POWERING) {
    (void)zs_dual_sim_complete_action(
        controller, ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS, false, now_ms);
    return false;
  }
  return zs_dual_sim_complete_action(
      controller, ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS, true, now_ms);
}

bool zs_dual_sim_bg95_confirm_modem_on(zs_dual_sim_t *controller,
                                       const zs_bg95_t *modem,
                                       bool cell_status_high,
                                       uint32_t now_ms) {
  if (!modem || !cell_status_high ||
      !action_is(controller, ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON) ||
      modem->state < ZS_BG95_AT_SYNC || modem->state >= ZS_BG95_POWERING_OFF)
    return false;
  return zs_dual_sim_complete_action(
      controller, ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON, true, now_ms);
}

bool zs_dual_sim_bg95_verify_iccid(zs_dual_sim_t *controller,
                                   const zs_bg95_t *modem) {
  const zs_bg95_network_settings_t *settings;
  if (!modem || !action_is(controller,
                           ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID))
    return false;
  settings = zs_bg95_get_network_settings(modem);
  if (!settings || !full_iccid_available(settings->iccid)) return false;
  return zs_dual_sim_on_iccid(controller, settings->iccid);
}

bool zs_dual_sim_bg95_confirm_link(zs_dual_sim_t *controller,
                                   const zs_bg95_t *modem,
                                   uint32_t now_ms) {
  const zs_bg95_network_settings_t *settings;
  if (!modem || !action_is(controller,
                           ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS) ||
      !zs_bg95_online(modem))
    return false;
  settings = zs_bg95_get_network_settings(modem);
  if (!settings || !settings->valid || settings->apn[0] == '\0' ||
      settings->local_address[0] == '\0' || settings->gateway[0] == '\0' ||
      settings->primary_dns[0] == '\0')
    return false;
  return zs_dual_sim_complete_action(
      controller, ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS, true, now_ms);
}
