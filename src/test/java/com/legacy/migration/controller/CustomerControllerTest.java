package com.legacy.migration.controller;

import com.legacy.migration.model.Customer;
import com.legacy.migration.service.CustomerService;
import org.junit.Before;
import org.junit.Test;
import org.springframework.http.ResponseEntity;

import java.util.List;

import static org.junit.Assert.*;

public class CustomerControllerTest {

    private CustomerController controller;

    @Before
    public void setUp() {
        controller =
                new CustomerController(new CustomerService());
    }

    @Test
    public void shouldReturnAllCustomers() {
        List<Customer> customers =
                controller.getAllCustomers();

        assertEquals(2, customers.size());
    }

    @Test
    public void shouldReturnExistingCustomer() {
        ResponseEntity<Customer> response =
                controller.getCustomerById(1L);

        assertEquals(200, response.getStatusCodeValue());
        assertNotNull(response.getBody());
        assertEquals("John Doe", response.getBody().getName());
    }

    @Test
    public void shouldReturnNotFoundForUnknownCustomer() {
        ResponseEntity<Customer> response =
                controller.getCustomerById(999L);

        assertEquals(404, response.getStatusCodeValue());
        assertNull(response.getBody());
    }

    @Test
    public void shouldCreateCustomer() {
        Customer customer =
                new Customer(null, "Bob", "bob@example.com");

        ResponseEntity<Customer> response =
                controller.createCustomer(customer);

        assertEquals(201, response.getStatusCodeValue());
        assertNotNull(response.getBody());
        assertNotNull(response.getBody().getId());
    }
}