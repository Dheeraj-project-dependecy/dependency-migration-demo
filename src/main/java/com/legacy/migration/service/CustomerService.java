package com.legacy.migration.service;

import com.legacy.migration.model.Customer;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class CustomerService {

    private final Map<Long, Customer> customers =
            new LinkedHashMap<Long, Customer>();

    private long nextId = 3L;

    public CustomerService() {
        customers.put(1L,
                new Customer(1L, "John Doe", "john@example.com"));
        customers.put(2L,
                new Customer(2L, "Alice Smith", "alice@example.com"));
    }

    public List<Customer> getAllCustomers() {
        return new ArrayList<Customer>(customers.values());
    }

    public Customer getCustomerById(Long id) {
        return customers.get(id);
    }

    public Customer createCustomer(Customer customer) {
        if (customer == null) {
            throw new IllegalArgumentException("Customer must not be null");
        }

        customer.setId(nextId++);
        customers.put(customer.getId(), customer);
        return customer;
    }
}