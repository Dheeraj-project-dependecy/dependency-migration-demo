package com.legacy.migration.service;

import com.legacy.migration.model.Customer;
import org.junit.Before;
import org.junit.Test;

import java.util.List;

import static org.junit.Assert.*;

public class CustomerServiceTest {

    private CustomerService customerService;

    @Before
    public void setUp() {
        customerService = new CustomerService();
    }

    @Test
    public void shouldReturnAllCustomers() {
        List<Customer> customers =
                customerService.getAllCustomers();

        assertEquals(2, customers.size());
    }

    @Test
    public void shouldReturnCustomerById() {
        Customer customer =
                customerService.getCustomerById(1L);

        assertNotNull(customer);
        assertEquals("John Doe", customer.getName());
    }

    @Test
    public void shouldReturnNullForUnknownCustomer() {
        Customer customer =
                customerService.getCustomerById(999L);

        assertNull(customer);
    }

    @Test
    public void shouldCreateCustomer() {
        Customer customer =
                new Customer(null, "Bob", "bob@example.com");

        Customer created =
                customerService.createCustomer(customer);

        assertNotNull(created.getId());
        assertEquals("Bob", created.getName());
        assertEquals(3, customerService.getAllCustomers().size());
    }

    @Test(expected = IllegalArgumentException.class)
    public void shouldRejectNullCustomer() {
        customerService.createCustomer(null);
    }
}