package com.avaliance.copilot.config.enums;

/**
 * Application roles — used in Spring Security authorities and JWT claims.
 */
public enum Role {

    ADMIN,
    CONSULTANT;

    /** Returns the Spring Security authority string (e.g. "ROLE_ADMIN"). */
    public String authority() {
        return "ROLE_" + this.name();
    }
}
